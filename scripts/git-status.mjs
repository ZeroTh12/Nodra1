// List files changed vs HEAD (isomorphic-git statusMatrix, .gitignore respected).
import git from 'isomorphic-git';
import fs from 'node:fs';

const dir = process.cwd();
const matrix = await git.statusMatrix({ fs, dir });
let changed = 0;
for (const [filepath, head, workdir] of matrix) {
  // workdir bits: 0=deleted 1=unchanged-size 2=changed-size; file content via head bit
  if (workdir === 0) { console.log(`DELETED  ${filepath}`); changed++; }
  else if (head === 0) { console.log(`NEW      ${filepath}`); changed++; }
  else if (workdir !== 1) { console.log(`MODIFIED ${filepath}`); changed++; }
}
console.log(changed === 0 ? '(clean)' : `total: ${changed}`);
