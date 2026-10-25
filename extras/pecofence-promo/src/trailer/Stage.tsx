import React from "react";
import {AbsoluteFill, Freeze, Img, OffthreadVideo, staticFile} from "remotion";
import {clamp01, ease, Ease, mix} from "./timing";

/** Native captures are 3840 × 2160 physical pixels at 200 % scaling. */
export const STAGE_W = 3840;
export const STAGE_H = 2160;

/** Camera looking at the stage: centre point in stage px, zoom (output px per stage px), rotations in degrees. */
export type Cam = {cx: number; cy: number; z: number; rx: number; ry: number; rz: number};
export type CamKey = Partial<Cam> & {t: number; e?: Ease};

const PROPS: (keyof Cam)[] = ["cx", "cy", "z", "rx", "ry", "rz"];

/** Interpolates camera keys; each key's easing shapes the move that ends on it. Unset values carry over. */
export const camAt = (t: number, keys: CamKey[]): Cam => {
  const full: (Cam & {t: number; e?: Ease})[] = [];
  let prev: Cam = {cx: STAGE_W / 2, cy: STAGE_H / 2, z: 0.5, rx: 0, ry: 0, rz: 0};
  for (const k of keys) {
    const c = {...prev};
    for (const p of PROPS) if (k[p] !== undefined) c[p] = k[p] as number;
    full.push({...c, t: k.t, e: k.e});
    prev = c;
  }
  if (t <= full[0].t) return full[0];
  for (let i = 1; i < full.length; i++) {
    const a = full[i - 1];
    const b = full[i];
    if (t <= b.t) {
      const x = (b.e ?? ease.inOut)(clamp01((t - a.t) / (b.t - a.t)));
      const out = {} as Cam;
      // Zoom interpolates geometrically so dolly speed feels constant.
      for (const p of PROPS) out[p] = p === "z" ? a.z * Math.pow(b.z / a.z, x) : mix(a[p], b[p], x);
      return out;
    }
  }
  return full[full.length - 1];
};

/** A 3840 × 2160 stage seen through the camera, with real perspective for the rotations. */
export const Stage: React.FC<{cam: Cam; children: React.ReactNode; style?: React.CSSProperties}> = ({cam, children, style}) => (
  <AbsoluteFill style={{perspective: 2400, perspectiveOrigin: "960px 540px", overflow: "hidden", ...style}}>
    <div style={{
      position: "absolute", left: 0, top: 0, width: STAGE_W, height: STAGE_H, transformOrigin: "0 0",
      transformStyle: "preserve-3d",
      transform: `translate(960px, 540px) rotateX(${cam.rx}deg) rotateY(${cam.ry}deg) rotateZ(${cam.rz}deg) scale(${cam.z}) translate(${-cam.cx}px, ${-cam.cy}px)`,
    }}>
      {children}
    </div>
  </AbsoluteFill>
);

/** One frame of a native take at `at` seconds of source time (60 fps sources). */
export const Take: React.FC<{src: string; at: number; style?: React.CSSProperties}> = ({src, at, style}) => (
  <Freeze frame={Math.max(0, Math.round(at * 60))}>
    <OffthreadVideo src={staticFile(`trailer-v3/${src}.mp4`)} muted
      style={{position: "absolute", left: 0, top: 0, width: STAGE_W, height: STAGE_H, ...style}}/>
  </Freeze>
);

/** A full-resolution still of a take (static moments render faster from PNG). */
export const Still: React.FC<{name: string; style?: React.CSSProperties}> = ({name, style}) => (
  <Img src={staticFile(`trailer-v3/stills/${name}.png`)}
    style={{position: "absolute", left: 0, top: 0, width: STAGE_W, height: STAGE_H, ...style}}/>
);

export type Rect = {x: number; y: number; w: number; h: number};

/** Shows only `rect` (+ margin) of a full-stage layer, e.g. one fence of a still. */
export const Window: React.FC<{rect: Rect; margin?: number; radius?: number; style?: React.CSSProperties; children: React.ReactNode}> = ({rect, margin = 60, radius = 40, style, children}) => (
  <div style={{
    position: "absolute", left: rect.x - margin, top: rect.y - margin, width: rect.w + margin * 2, height: rect.h + margin * 2,
    overflow: "hidden", borderRadius: radius, transformOrigin: "50% 50%", ...style,
  }}>
    <div style={{position: "absolute", left: -(rect.x - margin), top: -(rect.y - margin), width: STAGE_W, height: STAGE_H}}>
      {children}
    </div>
  </div>
);
