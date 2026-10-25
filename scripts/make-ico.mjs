// Assemble a multi-size ICO (PNG-compressed entries, Vista+) from scripts/icon-sizes/.
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const SIZES = [16, 24, 32, 48, 64, 128, 256];
const pngs = SIZES.map((s) => readFileSync(join("scripts", "icon-sizes", `icon-${s}.png`)));

const header = Buffer.alloc(6);
header.writeUInt16LE(0, 0); // reserved
header.writeUInt16LE(1, 2); // icon
header.writeUInt16LE(SIZES.length, 4);

const entries = [];
const datas = [];
let offset = 6 + SIZES.length * 16;
SIZES.forEach((s, i) => {
  const e = Buffer.alloc(16);
  e.writeUInt8(s === 256 ? 0 : s, 0);
  e.writeUInt8(s === 256 ? 0 : s, 1);
  e.writeUInt8(0, 2); // palette
  e.writeUInt8(0, 3); // reserved
  e.writeUInt16LE(1, 4); // planes
  e.writeUInt16LE(32, 6); // bpp
  e.writeUInt32LE(pngs[i].length, 8);
  e.writeUInt32LE(offset, 12);
  offset += pngs[i].length;
  entries.push(e);
  datas.push(pngs[i]);
});

const ico = Buffer.concat([header, ...entries, ...datas]);
const out = join("crates", "app", "assets", "pecofence.ico");
writeFileSync(out, ico);
console.log(`ico written: ${out} (${ico.length} bytes, ${SIZES.length} sizes)`);
