import React from "react";
import {AbsoluteFill, Img, random, staticFile} from "remotion";
import {camAt, CamKey, Stage, Still, Take, Window} from "../Stage";
import {centre, targets} from "../targets";
import {clamp01, cues, ease, mix, prog} from "../timing";
import {FONT_DISPLAY, FONT_TEXT, INK, INK_SOFT, Mark, useTime, Words} from "../Type";

/** What a messy desktop holds: the 15 files that end up in the fences, plus strays. */
type Clutter = {name: string; img: string; thumb?: boolean; fence?: string};
const FILES: Clutter[] = [
  {name: "Archive", img: "icons/folder.png", fence: "Projects"},
  {name: "Brand", img: "icons/folder.png", fence: "Projects"},
  {name: "Campaign", img: "icons/folder.png", fence: "Projects"},
  {name: "Website", img: "icons/folder.png", fence: "Projects"},
  {name: "Creative brief.pdf", img: "icons/pdf.png", fence: "Projects"},
  {name: "Launch checklist.md", img: "icons/md.png", fence: "Projects"},
  {name: "Atelier study.png", img: "icons/thumb-atelier-study.png", thumb: true, fence: "Inspiration"},
  {name: "Form study.png", img: "icons/thumb-form-study.png", thumb: true, fence: "Inspiration"},
  {name: "Sol study.png", img: "icons/thumb-sol-study.png", thumb: true, fence: "Inspiration"},
  {name: "Still study.png", img: "icons/thumb-still-study.png", thumb: true, fence: "Inspiration"},
  {name: "Terra study.png", img: "icons/thumb-terra-study.png", thumb: true, fence: "Inspiration"},
  {name: "Tide study.png", img: "icons/thumb-tide-study.png", thumb: true, fence: "Inspiration"},
  {name: "Creative brief.pdf", img: "icons/pdf.png", fence: "Today"},
  {name: "Meeting notes.txt", img: "icons/txt.png", fence: "Today"},
  {name: "Launch checklist.md", img: "icons/md.png", fence: "Today"},
  {name: "Screenshot 2026-09-12 104233.png", img: "clutter/clutter-shot-chat.png", thumb: true},
  {name: "Screenshot 2026-09-18 091507.png", img: "clutter/clutter-shot-dashboard.png", thumb: true},
  {name: "Screenshot (14).png", img: "clutter/clutter-shot-docs.png", thumb: true},
  {name: "IMG_2031.jpg", img: "clutter/clutter-photo-mountains.png", thumb: true},
  {name: "Untitled (3).txt", img: "icons/txt.png"},
  {name: "final_v7_REAL.pdf", img: "icons/pdf.png"},
  {name: "Invoice 0926.pdf", img: "icons/pdf.png"},
  {name: "notes-old.txt", img: "icons/txt.png"},
  {name: "Contract.pdf", img: "icons/pdf.png"},
  {name: "IMG_2033.jpg", img: "icons/png-generic.png"},
  {name: "photo_0412.jpg", img: "clutter/clutter-photo-sea.png", thumb: true},
  {name: "Screenshot (15).png", img: "clutter/clutter-shot-gallery.png", thumb: true},
  {name: "receipt-0917.png", img: "clutter/clutter-receipt.png", thumb: true},
  ...([
    ["Screenshot 2026-09-20 181102.png", "clutter/clutter-shot-gallery.png", 1], ["IMG_2044.jpg", "clutter/clutter-photo-sea.png", 1],
    ["draft-final.txt", "icons/txt.png", 0], ["Report (1).pdf", "icons/pdf.png", 0], ["scan0001.pdf", "icons/pdf.png", 0],
    ["todo.txt", "icons/txt.png", 0], ["memo.png", "clutter/clutter-memo.png", 1], ["Screenshot (16).png", "clutter/clutter-shot-chat.png", 1],
    ["Screenshot (17).png", "clutter/clutter-shot-docs.png", 1], ["New folder", "icons/folder.png", 0], ["New folder (2)", "icons/folder.png", 0],
    ["Old stuff", "icons/folder.png", 0], ["IMG_2090.heic", "icons/png-generic.png", 0], ["wallpaper.png", "clutter/clutter-photo-mountains.png", 1],
    ["notes (copy).txt", "icons/txt.png", 0], ["Q3 report (1).pdf", "icons/pdf.png", 0], ["export_v2.png", "clutter/clutter-shot-dashboard.png", 1],
    ["untitled.txt", "icons/txt.png", 0], ["brief-old.pdf", "icons/pdf.png", 0], ["IMG_2051.jpg", "clutter/clutter-photo-sea.png", 1],
    ["Screenshot (18).png", "clutter/clutter-shot-gallery.png", 1], ["meeting-notes-final.txt", "icons/txt.png", 0], ["Downloads backup", "icons/folder.png", 0],
    ["invoice-copy.pdf", "icons/pdf.png", 0], ["sketch.png", "clutter/clutter-memo.png", 1], ["readme.txt", "icons/txt.png", 0],
    ["photo_0420.jpg", "clutter/clutter-photo-mountains.png", 1], ["Screenshot (19).png", "clutter/clutter-shot-chat.png", 1],
  ] as const).map(([name, img, thumb]) => ({name, img, thumb: thumb === 1})),
];

const DESK_ICON = 110; // a little larger than 48 DIP desktop icons at 200 %, to read at 1080p
const FLY = 4.0;

type Placed = Clutter & {x: number; y: number; pop: number; tx: number; ty: number; ts: number; delay: number; dur: number; spin: number; arc: number; stray: boolean};

/** Deterministic messy layout: jittered desktop-grid cells, leaving the headline area clear. */
const layout = (): Placed[] => {
  const cells: {x: number; y: number}[] = [];
  for (let cx = 0; cx < 14; cx++) {
    for (let cy = 0; cy < 7; cy++) {
      const x = 640 + cx * 196;
      const y = 380 + cy * 224;
      if (x > 900 && x < 2950 && y > 880 && y < 1290) continue;
      cells.push({x, y});
    }
  }
  const order = cells.map((c, i) => ({c, k: random(`cell-${i}`)})).sort((a, b) => a.k - b.k).map((o) => o.c);
  const popOrder = FILES.map((_, i) => ({i, k: random(`pop-${i}`)})).sort((a, b) => a.k - b.k).map((o) => o.i);
  const popTimes = cues.sfx.filter((s) => s.type === "pop" && s.t < 3.5).map((s) => s.t);
  const items = targets.overview.items;
  return FILES.map((file, i) => {
    const cell = order[i];
    const x = cell.x + (random(`jx-${i}`) - 0.5) * 70;
    const y = cell.y + (random(`jy-${i}`) - 0.5) * 60;
    const match = file.fence ? items.find((it) => it.fence === file.fence && it.name === file.name) : undefined;
    let tx: number, ty: number, ts: number;
    if (match) {
      const c = centre(match.icon);
      tx = c.x; ty = c.y; ts = match.icon.w / DESK_ICON;
    } else {
      // Strays are absorbed by the nearest fence.
      const fences = Object.values(targets.overview.fences);
      const near = fences.map((r) => ({r, d: Math.hypot(centre(r).x - x, centre(r).y - y)})).sort((a, b) => a.d - b.d)[0].r;
      tx = near.x + near.w * (0.25 + random(`tx-${i}`) * 0.5);
      ty = near.y + near.h * (0.35 + random(`ty-${i}`) * 0.4);
      ts = 0.35;
    }
    const dist = Math.hypot(tx - x, ty - y);
    return {
      ...file, x, y, tx, ty, ts, stray: !match,
      // Two icons per pop cue; the second lands a 32nd later.
      pop: (popTimes[Math.floor(popOrder.indexOf(i) / 2)] ?? 2.9) + (popOrder.indexOf(i) % 2) * 0.0625,
      delay: (i % 7) * 0.02 + random(`d-${i}`) * 0.05,
      dur: 0.38 + Math.min(0.2, dist / 12000),
      spin: (random(`s-${i}`) - 0.5) * 30,
      arc: (random(`a-${i}`) - 0.5) * 0.5,
    };
  });
};
const PLACED = layout();

const flight = (p: Placed, t: number) => {
  const u = clamp01((t - FLY - p.delay) / p.dur);
  // Strong in-out so icons snap into place on the downbeat after the hit.
  const e = u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2;
  const mx = (p.x + p.tx) / 2 + (p.ty - p.y) * p.arc;
  const my = (p.y + p.ty) / 2 - (p.tx - p.x) * p.arc;
  const bx = (1 - e) * (1 - e) * p.x + 2 * (1 - e) * e * mx + e * e * p.tx;
  const by = (1 - e) * (1 - e) * p.y + 2 * (1 - e) * e * my + e * e * p.ty;
  return {u, e, x: bx, y: by};
};

const DesktopIcon: React.FC<{p: Placed; t: number}> = ({p, t}) => {
  const pop = clamp01((t - p.pop) / 0.28);
  if (pop <= 0) return null;
  const popScale = pop < 1 ? 0.35 + 0.65 * ease.out(pop) + Math.sin(pop * Math.PI) * 0.12 : 1;
  // Anticipation: tremble and lean towards the target just before the hit.
  const tense = prog(t, 3.35, 0.65, ease.in);
  const jitter = tense * 5 * Math.sin(t * 70 + p.x);
  const lean = tense * 0.035;
  const f = flight(p, t);
  const flying = f.u > 0;
  const x = flying ? f.x : mix(p.x, p.tx, lean) + jitter;
  const y = flying ? f.y : mix(p.y, p.ty, lean) + jitter * 0.6;
  const s = flying ? mix(1, p.ts, f.e) : popScale * (1 - tense * 0.06);
  const rot = flying ? Math.sin(f.e * Math.PI) * p.spin : 0;
  // Named files hand over to the native pixels as the glass forms; strays sink into it.
  const fade = p.stray ? 1 - clamp01((f.u - 0.62) / 0.38) : 1 - prog(t, 4.46, 0.2, ease.linear);
  const labelOpacity = 1 - prog(t, 3.72, 0.22, ease.linear);
  if (fade <= 0) return null;
  const size = DESK_ICON;
  const ghosts = flying && f.u < 1 ? [6, 5, 4, 3, 2, 1] : [];
  const body = (key: string, gx: number, gy: number, op: number) => (
    <div key={key} style={{position: "absolute", left: gx - size / 2, top: gy - size / 2, width: size, height: size,
      transform: `scale(${s}) rotate(${rot}deg)`, opacity: op}}>
      {p.thumb ? (
        <Img src={staticFile(`trailer-v3/${p.img}`)} style={{width: size, height: size, objectFit: "contain",
          filter: "drop-shadow(0 3px 6px #0006)"}}/>
      ) : (
        <Img src={staticFile(`trailer-v3/${p.img}`)} style={{width: size, height: size, filter: "drop-shadow(0 3px 5px #0005)"}}/>
      )}
    </div>
  );
  return (
    <>
      {ghosts.map((g) => {
        const gf = flight(p, t - g * 0.0042);
        return body(`g${g}`, gf.x, gf.y, fade * 0.3 * (7 - g) / 6);
      })}
      {body("main", x, y, fade)}
      {labelOpacity > 0 && !flying && (
        <div style={{position: "absolute", left: x - 104, top: y + size / 2 + 6, width: 208, textAlign: "center",
          font: `400 26px/1.25 ${FONT_TEXT}`, color: "#fff", textShadow: "0 1px 3px #000c, 0 0 8px #0008",
          opacity: labelOpacity * clamp01(pop * 2), display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden",
          wordBreak: "break-word"}}>{p.name}</div>
      )}
    </>
  );
};

/** A specular glint that crosses a glass panel once. */
export const Glint: React.FC<{t: number; at: number; dur?: number; strength?: number}> = ({t, at, dur = 0.7, strength = 0.55}) => {
  const u = (t - at) / dur;
  if (u < 0 || u > 1) return null;
  const pos = mix(-40, 140, ease.inOut(u));
  return <div style={{position: "absolute", inset: 0, mixBlendMode: "screen", opacity: strength * Math.sin(u * Math.PI),
    background: `linear-gradient(105deg, transparent ${pos - 22}%, #ffffff66 ${pos - 6}%, #ffffffcc ${pos}%, #ffffff55 ${pos + 5}%, transparent ${pos + 20}%)`}}/>;
};

const CAM: CamKey[] = [
  {t: 0, cx: 1920, cy: 1080, z: 0.66, rz: -1.2},
  {t: 3.4, z: 0.72, rz: 0, e: ease.soft},
  {t: 4.0, z: 0.7, e: ease.in},
  // Frame the three fences under the brand title.
  {t: 4.8, cx: 1917, cy: 965, z: 0.7, e: ease.out},
  {t: 8.2, cx: 1910, cy: 952, z: 0.74, ry: 0, e: ease.soft},
];

const FENCE_REVEAL: Record<string, number> = {Projects: 4.4, Inspiration: 4.46, Today: 4.52};

export const Opening: React.FC = () => {
  const t = useTime();
  const cam = camAt(t, CAM);
  const fences = targets.overview.fences;
  // Light sweep: the dark desk turns into the light one from left to right.
  const sweep = prog(t, 4.95, 0.9, ease.inOut);
  const sweepPos = mix(-25, 125, sweep);
  const lightMask = `linear-gradient(100deg, #000 ${sweepPos - 12}%, transparent ${sweepPos + 12}%)`;
  const introDim = 1 - prog(t, 0, 0.5, ease.soft);
  return (
    <AbsoluteFill style={{background: "#141726"}}>
      <Stage cam={cam}>
        {/* Wallpaper-only frame of the dark take: the same pixels the fences are later captured on. */}
        <Take src="dark" at={1.0}/>
        {Object.entries(fences).map(([name, rect]) => {
          const p = prog(t, FENCE_REVEAL[name], 0.42, ease.out);
          if (p <= 0) return null;
          return (
            <Window key={name} rect={rect} margin={70} radius={44}
              style={{opacity: clamp01(p * 1.4), transform: `scale(${mix(0.9, 1, p)})`, filter: p < 1 ? `blur(${mix(18, 0, p)}px)` : undefined}}>
              <Still name="dark-4s"/>
            </Window>
          );
        })}
        {sweep > 0 && (
          <div style={{position: "absolute", inset: 0, WebkitMaskImage: lightMask, maskImage: lightMask}}>
            <Still name="overview-4s"/>
          </div>
        )}
        {Object.entries(fences).map(([name, rect]) => (
          <div key={`g-${name}`} style={{position: "absolute", left: rect.x, top: rect.y, width: rect.w, height: rect.h, borderRadius: 24, overflow: "hidden"}}>
            <Glint t={t} at={FENCE_REVEAL[name] + 0.18} dur={0.8}/>
            <Glint t={t} at={5.25 + (rect.x / 3840) * 0.6} dur={0.75} strength={0.4}/>
          </div>
        ))}
        {PLACED.map((p, i) => <DesktopIcon key={i} p={p} t={t}/>)}
      </Stage>
      {/* Warm bloom that rides the light sweep. */}
      {sweep > 0 && sweep < 1 && (
        <AbsoluteFill style={{mixBlendMode: "screen", opacity: Math.sin(sweep * Math.PI) * 0.7,
          background: `linear-gradient(100deg, transparent ${sweepPos - 18}%, #ffe7cf88 ${sweepPos - 2}%, #fff6ecaa ${sweepPos}%, transparent ${sweepPos + 16}%)`}}/>
      )}
      {/* Intro copy over the clutter. */}
      <AbsoluteFill style={{justifyContent: "center", alignItems: "center", pointerEvents: "none"}}>
        <div style={{position: "absolute", top: 440, width: "100%", display: "flex", justifyContent: "center"}}>
          <Words text="Screenshots. Downloads. Drafts." start={0.5} end={2.18} exitDur={0.26} stagger={0.5} dur={0.55}
            style={{font: `600 92px/1.1 ${FONT_DISPLAY}`, color: "#fff", letterSpacing: "-0.025em", justifyContent: "center",
              textShadow: "0 2px 4px #0007, 0 8px 40px #0009"}}/>
        </div>
        <div style={{position: "absolute", top: 440, width: "100%", display: "flex", justifyContent: "center"}}>
          <Words text="Everywhere." start={2.5} end={3.7} dur={0.55} exitDur={0.25}
            style={{font: `650 118px/1.1 ${FONT_DISPLAY}`, color: "#fff", letterSpacing: "-0.03em", justifyContent: "center",
              textShadow: "0 2px 4px #0007, 0 8px 40px #0009"}}/>
        </div>
      </AbsoluteFill>
      {/* Brand title over the assembled fences. */}
      <AbsoluteFill style={{alignItems: "center", pointerEvents: "none"}}>
        <div style={{position: "absolute", top: 118, display: "flex", alignItems: "center", gap: 30}}>
          <div style={{opacity: prog(t, 4.62, 0.3, ease.linear), transform: `scale(${mix(0.6, 1, prog(t, 4.62, 0.7))})`}}>
            <Mark size={96} color={mixInk(t)} draw={prog(t, 4.62, 0.8)} tiles={prog(t, 4.95, 0.7, ease.linear)}/>
          </div>
          <Words text="PecoFence" start={4.7} end={7.72} dur={0.8}
            style={{font: `650 118px/1 ${FONT_DISPLAY}`, color: mixInk(t), letterSpacing: "-0.03em"}}/>
        </div>
        <div style={{position: "absolute", top: 262, width: "100%", display: "flex", justifyContent: "center"}}>
          <Words text="Make room for what matters." start={5.55} end={7.72} stagger={0.06}
            style={{font: `500 50px/1.2 ${FONT_DISPLAY}`, color: mixSoft(t), letterSpacing: "-0.015em", justifyContent: "center"}}/>
        </div>
      </AbsoluteFill>
      <AbsoluteFill style={{background: "#000", opacity: introDim, pointerEvents: "none"}}/>
    </AbsoluteFill>
  );
};

/** Title colour follows the light sweep: white on the dark desk, ink on the light one. */
const lerpHex = (a: string, b: string, x: number) => {
  const pa = [1, 3, 5].map((i) => parseInt(a.slice(i, i + 2), 16));
  const pb = [1, 3, 5].map((i) => parseInt(b.slice(i, i + 2), 16));
  return `rgb(${pa.map((v, i) => Math.round(mix(v, pb[i], x))).join(",")})`;
};
const mixInk = (t: number) => lerpHex("#ffffff", INK, prog(t, 5.15, 0.6, ease.inOut));
const mixSoft = (t: number) => lerpHex("#e8e6f2", INK_SOFT, prog(t, 5.15, 0.6, ease.inOut));
