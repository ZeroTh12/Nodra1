// Muxes the mastered soundtrack into the rendered trailer and writes the delivery files.
//   node scripts/render.mjs --trailer      (silent 1080p60 picture)
//   node scripts/finish-trailer.mjs
// Outputs in out/:
//   PecoFence-trailer-v3-1080p60.mp4  master (H.264 High, 60 fps, AAC 320k)
//   PecoFence-trailer-v3-store-1080p30.mp4  Microsoft Store upload (1920x1080, 30 fps)
//   PecoFence-trailer-v3-web-720p.mp4  site embed (1280x720, 30 fps, small)
//   PecoFence-trailer-v3-thumbnail.png  1920x1080 Store thumbnail (a frame of the trailer)
import {execFileSync} from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const out = path.join(root, "out");
const picture = path.join(out, "trailer-v3", "work", "PecoFence-trailer-v3-1080p60-picture.mp4");
const audio = path.join(root, "public", "trailer-v3", "audio", "final", "soundtrack.wav");
const thumbFrame = Number(process.argv.find((a) => a.startsWith("--thumb="))?.slice(8) ?? 1488);
for (const f of [picture, audio]) if (!fs.existsSync(f)) throw new Error(`Missing ${f}`);

const bt709 = ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv"];
const run = (args) => {
  console.log("ffmpeg", args.filter((a) => !a.includes(root)).slice(-6).join(" "));
  execFileSync("ffmpeg", ["-hide_banner", "-loglevel", "error", "-y", ...args], {stdio: "inherit"});
};

// Master: picture stream copied bit-exact, audio encoded once from the 24-bit master.
run(["-i", picture, "-i", audio, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
  "-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-shortest", "-movflags", "+faststart",
  path.join(out, "PecoFence-trailer-v3-1080p60.mp4")]);

// Store: 30 fps (Partner Center prefers ~30 fps), high bitrate, closed GOP.
run(["-i", picture, "-i", audio, "-map", "0:v:0", "-map", "1:a:0",
  "-vf", "fps=30", "-c:v", "libx264", "-preset", "slow", "-crf", "12", "-profile:v", "high", "-level", "4.2",
  "-pix_fmt", "yuv420p", "-g", "30", "-bf", "2", ...bt709,
  "-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-shortest", "-movflags", "+faststart",
  path.join(out, "PecoFence-trailer-v3-store-1080p30.mp4")]);

// Web: 720p for the product site's <video> element.
run(["-i", picture, "-i", audio, "-map", "0:v:0", "-map", "1:a:0",
  "-vf", "fps=30,scale=1280:720:flags=lanczos", "-c:v", "libx264", "-preset", "slow", "-crf", "21",
  "-profile:v", "high", "-pix_fmt", "yuv420p", ...bt709,
  "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-shortest", "-movflags", "+faststart",
  path.join(out, "PecoFence-trailer-v3-web-720p.mp4")]);

run(["-ss", (thumbFrame / 60).toFixed(4), "-i", picture, "-frames:v", "1", "-update", "1",
  path.join(out, "PecoFence-trailer-v3-thumbnail.png")]);
console.log("Delivery files written to out/.");
