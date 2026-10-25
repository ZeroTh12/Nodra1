import assert from 'node:assert/strict';
import { test } from 'node:test';
import worker, { issueFor, validate } from '../src/index.js';

const report = (overrides = {}) => ({
  kind: 'bug',
  message: 'Fences vanish after sleep',
  email: null,
  app: '0.1.4',
  language: 'zh-CN',
  crash: false,
  system: { app: 'PecoFence 0.1.4 (ZIP / winget)', windows: 'build 26200' },
  log: '2026-10-04T12:00:00Z  INFO pecofence::app: config loaded fences=7',
  ...overrides,
});

const post = (body, headers = {}) =>
  new Request('https://api.pecofence.jiang.jp/feedback', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'CF-Connecting-IP': '203.0.113.7', ...headers },
    body: typeof body === 'string' ? body : JSON.stringify(body),
  });

/** Runs the worker with GitHub replaced by `github` (records the issue it was asked to file). */
async function run(request, { github = () => new Response('{}', { status: 201 }), limited = false } = {}) {
  const calls = [];
  const realFetch = globalThis.fetch;
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init, issue: JSON.parse(init.body) });
    return github();
  };
  const limiterKeys = [];
  const env = {
    GITHUB_REPO: 'DayuanJiang/PecoFence-feedback',
    GITHUB_TOKEN: 'test-token',
    LIMITER: { limit: async ({ key }) => (limiterKeys.push(key), { success: !limited }) },
  };
  try {
    const response = await worker.fetch(request, env);
    return { response, calls, limiterKeys };
  } finally {
    globalThis.fetch = realFetch;
  }
}

test('a valid report becomes an issue in the private repository', async () => {
  const { response, calls, limiterKeys } = await run(post(report({ email: 'jane@example.com', crash: true })));
  assert.equal(response.status, 201);
  assert.equal(response.headers.get('Access-Control-Allow-Origin'), '*');
  assert.deepEqual(limiterKeys, ['203.0.113.7']);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, 'https://api.github.com/repos/DayuanJiang/PecoFence-feedback/issues');
  assert.equal(calls[0].init.headers.Authorization, 'Bearer test-token');
  const { title, body, labels } = calls[0].issue;
  assert.equal(title, '[0.1.4] Fences vanish after sleep');
  assert.deepEqual(labels, ['bug', 'crash', 'has-log', 'has-contact']);
  assert.match(body, /### Message\n\n```text\nFences vanish after sleep\n```/);
  assert.match(body, /jane@example\.com/);
  assert.match(body, /windows: build 26200/);
  assert.match(body, /config loaded fences=7/);
  // The IP is only the rate-limit key.
  assert.doesNotMatch(JSON.stringify(calls[0].issue), /203\.0\.113\.7/);
});

test('user text cannot mention, link or break out of its code block', async () => {
  const message = 'hey @octocat see #12\n````\n<img src=x onerror=alert(1)>\n````';
  const { title, body } = issueFor(validate(report({ message })).report);
  assert.equal(title, '[0.1.4] hey ＠octocat see ＃12');
  // A five-backtick fence: the four-backtick lines inside cannot close it.
  assert.match(body, /`````text\nhey @octocat see #12\n````\n<img src=x onerror=alert\(1\)>\n````\n`````/);
});

test('long titles are cut on a character boundary', () => {
  const { title } = issueFor(validate(report({ message: '栅'.repeat(100) })).report);
  assert.equal([...title].length, '[0.1.4] '.length + 72);
  assert.ok(title.endsWith('…'));
});

test('optional parts may be left out', async () => {
  const { response, calls } = await run(post(report({ language: null, system: null, log: null })));
  assert.equal(response.status, 201);
  assert.deepEqual(calls[0].issue.labels, ['bug']);
  assert.match(calls[0].issue.body, /language: not sent/);
  assert.doesNotMatch(calls[0].issue.body, /### Log/);
});

test('bad reports are refused before GitHub is called', async () => {
  for (const [body, status] of [
    [report({ kind: 'spam' }), 400],
    [report({ message: '   ' }), 400],
    [report({ message: 'x'.repeat(5001) }), 400],
    [report({ email: 'not an email' }), 400],
    [report({ email: 'a@b.c<script>' }), 400],
    [report({ app: '../../etc' }), 400],
    [report({ system: { Path: 'C:\\Users' } }), 400],
    [report({ log: 'x'.repeat(53 * 1024) }), 400],
    ['{not json', 400],
  ]) {
    const { response, calls } = await run(post(body));
    assert.equal(response.status, status, JSON.stringify(body).slice(0, 60));
    assert.equal(calls.length, 0);
  }
});

test('protocol errors', async () => {
  const preflight = await worker.fetch(new Request('https://api.pecofence.jiang.jp/feedback', { method: 'OPTIONS' }), {});
  assert.equal(preflight.status, 204);
  assert.equal(preflight.headers.get('Access-Control-Allow-Headers'), 'Content-Type');
  assert.equal((await run(post(report(), { 'Content-Type': 'text/plain' }))).response.status, 415);
  assert.equal((await worker.fetch(new Request('https://api.pecofence.jiang.jp/feedback'), {})).status, 405);
  assert.equal((await worker.fetch(new Request('https://api.pecofence.jiang.jp/other'), {})).status, 404);
  assert.equal((await run(post(report()), { limited: true })).response.status, 429);
  assert.equal((await run(post('x'.repeat(70 * 1024)))).response.status, 413);
});

test('a GitHub failure is reported as 502 without echoing the report', async () => {
  const { response } = await run(post(report()), { github: () => new Response('{"message":"Bad credentials"}', { status: 401 }) });
  assert.equal(response.status, 502);
  assert.deepEqual(await response.json(), { error: 'could not file the report' });
});
