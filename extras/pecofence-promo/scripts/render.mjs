import fs from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";
import {bundle} from "@remotion/bundler";
import {openBrowser, renderMedia, renderStill, selectComposition} from "@remotion/renderer";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const out = path.join(root, "out");
const features=process.argv.includes("--features");
const launch=process.argv.includes("--launch");
const reviewed=process.argv.includes("--reviewed");
const trailer=process.argv.includes("--trailer");
const preview=process.argv.includes("--preview");
const nameArg=process.argv.find(a=>a.startsWith("--name="))?.slice(7);
if(nameArg&&!/^[A-Za-z0-9_-]+$/.test(nameArg))throw new Error("Output name must be a simple filename stem.");
const id=trailer?"PecoFence-Trailer":reviewed?"PecoFence-Reviewed":launch?"PecoFence-Launch":features?"PecoFence-Features":"PecoFence-Promo";
const outputName=nameArg??(preview?"trailer-v3/work/trailer-v3-preview":trailer?"trailer-v3/work/PecoFence-trailer-v3-1080p60-picture":reviewed?"PecoFence-autosort-en-1080p":launch?"PecoFence-launch-en-1080p":features?"PecoFence-features-en-1080p":"PecoFence-promo-en-1080p");
const posterFrame=trailer?1680:reviewed?835:launch?760:features?2200:835;
fs.mkdirSync(out, {recursive:true});
const browserExecutable = process.env.REMOTION_BROWSER_EXECUTABLE ??
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
console.log("Bundling Remotion composition...");
const serveUrl = await bundle({
  entryPoint:path.join(root,"src","index.ts"), rootDir:root,
  publicDir:path.join(root,"public"),outDir:path.join(root,".cache","bundle"),
  rspack:true,
});
const browser = await openBrowser("chrome", {browserExecutable,
  chromiumOptions:{gl:"angle"}});
try {
  const composition = await selectComposition({serveUrl,id,
    browserExecutable,puppeteerInstance:browser});
  console.log(`Composition: ${composition.width}x${composition.height}, ${composition.fps}fps, ${composition.durationInFrames} frames.`);
  if (process.argv.includes("--stills")) {
    const frameArg=process.argv.find(a=>a.startsWith("--frames="));
    const frames=frameArg?frameArg.slice(9).split(",").map(Number):
      (trailer?[60,150,230,262,275,300,330,420,560,640,700,760,850,900,1020,1080,1130,1180,1203,1215,1260,1330,1440,1520,1600,1700,1790]:reviewed?[12,30,60,140,195,205,210,218,245,300,400,447,475,550,610,665,689,705,730,800,875]:launch?[30,135,215,285,355,415,475,555,615,670,755,820]:features?[70,235,371,580,726,875,1080,1270,1435,1600,1690,1760,1940,2030,2070,2200]:[90,240,390,530,588,705,835]);
    for (const frame of frames) {
      await renderStill({serveUrl,composition,frame,output:path.join(out,`${trailer?"trailer-v3/":reviewed?"tech-":launch?"launch-":features?"feature-":""}frame-${frame}.png`),
        imageFormat:"png",browserExecutable,puppeteerInstance:browser,scale:reviewed||trailer?1:.75});
      console.log(`Verified render at frame ${frame}.`);
    }
  } else {
    let last = -1;
    await renderMedia({
      serveUrl,composition,codec:"h264",outputLocation:path.join(out,`${outputName}.mp4`),
      browserExecutable,puppeteerInstance:browser,crf:18,pixelFormat:"yuv420p",
      concurrency:trailer?6:4,imageFormat:reviewed||trailer?"png":"jpeg",jpegQuality:reviewed||trailer?undefined:92,
      colorSpace:reviewed||trailer?"bt709":undefined,
      ...(trailer?{crf:14,x264Preset:"slow",audioCodec:"aac",audioBitrate:"320k"}:{}),
      ...(preview?{scale:0.5,crf:23,x264Preset:"veryfast",imageFormat:"jpeg",jpegQuality:85}:{}),
      onProgress:({progress}) => {
        const percent = Math.floor(progress*20)*5;
        if (percent>last) {last=percent;console.log(`Rendering ${percent}%`);}
      },
    });
    await renderStill({serveUrl,composition,frame:posterFrame,output:path.join(out,reviewed||trailer?`${outputName}-poster.png`:launch?"PecoFence-launch-poster.png":features?"PecoFence-features-poster.png":"PecoFence-poster.png"),
      imageFormat:"png",browserExecutable,puppeteerInstance:browser});
    console.log("Exported MP4 and poster.");
  }
} finally {
  await browser.close({silent:true});
}
