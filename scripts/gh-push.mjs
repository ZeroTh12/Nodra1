/*
 * 推送辅助脚本:把当前分支推到 GitHub(需要仓库已存在)。
 * 用法: set GH_TOKEN=xxx && node scripts/gh-push.mjs
 * 可选环境变量: GH_USER(默认 ZeroTh12) GH_REPO(默认 Nodra)
 */
import git from 'isomorphic-git';
import http from 'isomorphic-git/http/node';
import fs from 'node:fs';

const dir = process.cwd();
const token = process.env.GH_TOKEN;
const user = process.env.GH_USER || 'ZeroTh12';
const repo = process.env.GH_REPO || 'Nodra';
const url = `https://github.com/${user}/${repo}.git`;

if (!token) {
  console.error('缺少 GH_TOKEN 环境变量');
  process.exit(1);
}

const branch = (await git.currentBranch({ fs, dir })) || 'master';
console.log(`pushing ${branch} -> ${url}`);

await git.addRemote({ fs, dir, remote: 'origin', url, force: true });
const result = await git.push({
  fs,
  http,
  dir,
  remote: 'origin',
  ref: branch,
  onAuth: () => ({ username: user, password: token }),
});
for (const [ref, ok] of Object.entries(result.refs ?? {})) {
  console.log(`  ${ref}: ${ok ? 'ok' : 'FAILED'}`);
}
console.log('✓ push 完成');
