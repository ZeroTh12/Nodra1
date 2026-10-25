# Feedback service

Receives reports from the settings page's 「反馈」 page and files each one as an issue in the
private repository `DayuanJiang/PecoFence-feedback`; GitHub then notifies the maintainer.
Live at `https://api.pecofence.jiang.jp/feedback` (Cloudflare Worker `pecofence-feedback`).

- `POST /feedback` with a JSON report (`kind`, `message`, optional `email`, `app`, and, when
  the user leaves the diagnostic log on, `language`, `system`, `log`). Answers `201`, or `400`
  (invalid report), `413` (over 64 KB), `415` (not JSON), `429` (more than 3 per minute from
  one IP), `502` (GitHub refused it).
- User text only appears inside code blocks in the issue, so it cannot mention people,
  reference issues or embed images; titles have `@` and `#123` neutralised.
- The client IP is the rate-limit key and nothing else. Do not enable observability or
  logpush on this Worker: request metadata (the IP) must not be kept.

Tests: `node --test` (no dependencies). Deploy: `npx wrangler deploy`. The token is a secret:
`npx wrangler secret put GITHUB_TOKEN` (fine-grained, Issues read/write on the feedback
repository only).

The app side: `crates/app/src/app/feedback.rs` (what may be sent), `crates/app/src/share_log.rs`
(the log that is safe to send) and the 「反馈」 page in `ui/settings.html`. A test instance can
post elsewhere with `PECOFENCE_FEEDBACK_URL` (an `https://` URL or `http://127.0.0.1:<port>`).
