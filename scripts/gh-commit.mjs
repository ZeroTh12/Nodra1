/*
 * 提交辅助脚本:本机无 git CLI,使用 isomorphic-git 完成暂存与提交(.gitignore 生效)。
 * 用法: node scripts/gh-commit.mjs "commit message"
 */
import git from 'isomorphic-git';
import fs from 'node:fs';
import path from 'node:path';

const dir = process.argv[3] ? path.resolve(process.argv[3]) : process.cwd();
const message = process.argv[2];

if (!message) {
  console.error('用法: node scripts/gh-commit.mjs "commit message"');
  process.exit(1);
}

try {
  await git.init({ fs, dir });
} catch {
  /* 已初始化则忽略 */
}

// stage all changes (respect .gitignore via statusMatrix)
const matrix = await git.statusMatrix({ fs, dir });
let added = 0, removed = 0;
for (const [filepath, head, workdir] of matrix) {
  if (workdir === 0) {
    await git.remove({ fs, dir, filepath });
    removed++;
  } else {
    await git.add({ fs, dir, filepath });
    added++;
  }
}

const sha = await git.commit({
  fs,
  dir,
  message,
  author: { name: 'pecofence-build', email: 'build@local' },
});

console.log(`✓ committed ${sha.slice(0, 8)}: ${message} (+${added} -${removed})`);
