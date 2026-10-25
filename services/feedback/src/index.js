// PecoFence feedback service. The app's settings page (「反馈」) posts a report here and it is
// filed as an issue in the private repository GITHUB_REPO, so GitHub notifies the maintainer.
//
// Secret: GITHUB_TOKEN, a fine-grained token with Issues read/write on that repository only.
// The client IP is used for rate limiting and nothing else: it is not logged, stored or
// forwarded.

const MAX_BODY = 64 * 1024;
const MAX_MESSAGE = 5000;
const MAX_LOG = 52 * 1024;
const KINDS = ['bug', 'idea', 'other'];
const GITHUB_API = 'https://api.github.com';

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
  'Access-Control-Max-Age': '86400',
};

function reply(status, body) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...CORS },
  });
}

const isString = (v, max) => typeof v === 'string' && v.length <= max;

/** Checks a report from the page; returns `{ report }` or `{ error }`. */
export function validate(input) {
  if (!input || typeof input !== 'object' || Array.isArray(input)) return { error: 'report must be an object' };
  const { kind, message, email = null, app, language = null, crash = false, system = null, log = null } = input;
  if (!KINDS.includes(kind)) return { error: 'unknown kind' };
  if (!isString(message, MAX_MESSAGE) || !message.trim()) return { error: 'message missing or too long' };
  if (email !== null && !(isString(email, 254) && /^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$/.test(email))) {
    return { error: 'invalid email' };
  }
  if (!isString(app, 32) || !/^[0-9A-Za-z.+-]+$/.test(app)) return { error: 'invalid app version' };
  if (language !== null && !(isString(language, 16) && /^[A-Za-z-]+$/.test(language))) return { error: 'invalid language' };
  if (typeof crash !== 'boolean') return { error: 'invalid crash flag' };
  if (system !== null) {
    if (typeof system !== 'object' || Array.isArray(system)) return { error: 'invalid system facts' };
    const entries = Object.entries(system);
    if (entries.length > 12 || entries.some(([k, v]) => !/^[a-z]{1,20}$/.test(k) || !isString(v, 200))) {
      return { error: 'invalid system facts' };
    }
  }
  if (log !== null && !isString(log, MAX_LOG)) return { error: 'log too long' };
  return { report: { kind, message: message.trim(), email, app, language, crash, system, log } };
}

/** A code fence no line of `text` can close: one backtick longer than its longest run. */
function fence(text) {
  const runs = text.match(/`+/g) || [];
  return '`'.repeat(Math.max(3, ...runs.map((r) => r.length + 1)));
}

function block(text, info = 'text') {
  const f = fence(text);
  return `${f}${info}\n${text}\n${f}`;
}

/** Plain-text title: the first line of the message, with nothing GitHub would link. */
function title(report) {
  const first = report.message.split('\n').find((l) => l.trim()) || '';
  let summary = first.trim().replace(/[\u0000-\u001f\u007f]/g, ' ').replace(/@/g, '＠').replace(/#(?=\d)/g, '＃');
  if ([...summary].length > 72) summary = [...summary].slice(0, 71).join('') + '…';
  return `[${report.app}] ${summary}`;
}

/** The issue for a validated report. User text only ever appears inside code blocks, so it
 * cannot mention people, reference issues, embed images or inject HTML. */
export function issueFor(report) {
  const labels = [report.kind];
  if (report.crash) labels.push('crash');
  if (report.log) labels.push('has-log');
  if (report.email) labels.push('has-contact');
  const parts = ['### Message', block(report.message)];
  parts.push('### Contact', report.email ? block(report.email) : '_none_');
  const facts = [`app: ${report.app}`, `language: ${report.language ?? 'not sent'}`, `crash: ${report.crash ? 'yes' : 'no'}`];
  for (const [k, v] of Object.entries(report.system || {})) facts.push(`${k}: ${v}`);
  parts.push('### System', block(facts.join('\n')));
  if (report.log) {
    const lines = report.log.split('\n').length;
    parts.push('### Log', `<details><summary>Shareable log, ${lines} lines</summary>\n\n${block(report.log)}\n\n</details>`);
  }
  parts.push('', '_Sent from the PecoFence settings page._');
  return { title: title(report), body: parts.join('\n\n'), labels };
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname !== '/feedback') return reply(404, { error: 'not found' });
    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: CORS });
    if (request.method !== 'POST') return reply(405, { error: 'POST only' });
    // JSON only: a plain cross-site form post cannot reach the issue tracker.
    if (!(request.headers.get('Content-Type') || '').toLowerCase().startsWith('application/json')) {
      return reply(415, { error: 'JSON only' });
    }
    if (Number(request.headers.get('Content-Length') || 0) > MAX_BODY) return reply(413, { error: 'too large' });
    if (env.LIMITER) {
      const { success } = await env.LIMITER.limit({ key: request.headers.get('CF-Connecting-IP') || 'unknown' });
      if (!success) return reply(429, { error: 'too many reports' });
    }
    const text = await request.text();
    if (text.length > MAX_BODY) return reply(413, { error: 'too large' });
    let input;
    try {
      input = JSON.parse(text);
    } catch {
      return reply(400, { error: 'invalid JSON' });
    }
    const { report, error } = validate(input);
    if (error) return reply(400, { error });

    const response = await fetch(`${env.GITHUB_API || GITHUB_API}/repos/${env.GITHUB_REPO}/issues`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'pecofence-feedback',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(issueFor(report)),
    });
    if (!response.ok) {
      // Status only: the response may echo the report.
      console.error('GitHub refused the issue', response.status);
      return reply(502, { error: 'could not file the report' });
    }
    return reply(201, { ok: true });
  },
};
