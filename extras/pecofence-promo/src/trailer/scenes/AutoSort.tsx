import React from "react";
import {AbsoluteFill, Img, staticFile} from "remotion";
import {camAt, CamKey, Stage, Take} from "../Stage";
import {centre, targets} from "../targets";
import {clamp01, cues, ease, eventAnchors, mix, remap} from "../timing";
import {ACCENT, Fade, FONT_DISPLAY, FONT_TEXT, INK, INK_SOFT, useTime, Words} from "../Type";

/** Native arrival times in auto.mp4 → beat-aligned timeline times (cues.json "land"). */
const LANDS = cues.sfx.filter((s) => s.type === "land").map((s) => s.t);
const ARRIVALS = [
  {name: "Form study.png", native: 5.783, img: "icons/thumb-form-study.png", thumb: true},
  {name: "Launch checklist.md", native: 6.933, img: "icons/md.png"},
  {name: "Sol study.png", native: 8.167, img: "icons/thumb-sol-study.png", thumb: true},
  {name: "Q3 report.pdf", native: 9.417, img: "icons/pdf.png"},
].map((a, i) => ({...a, t: LANDS[i]}));

const ANCHORS = eventAnchors(ARRIVALS.map((a) => [a.t, a.native] as const), 0.08, 0.6);

const CAM: CamKey[] = [
  {t: 7.75, cx: 2330, cy: 1060, z: 0.8, ry: -5},
  {t: 8.35, cx: 1930, cy: 1040, z: 0.8, ry: -1.5, e: ease.out},
  {t: 12.1, cx: 1990, cy: 1075, z: 0.87, ry: 1.5, e: ease.soft},
];

const FLIGHT = 0.62;

/** An incoming file dropping into its fence on the beat, handing over to the native item. */
const Incoming: React.FC<{a: (typeof ARRIVALS)[number]; t: number}> = ({a, t}) => {
  const target = targets.auto.arrivals[a.name];
  if (!target) return null;
  const u = (t - (a.t - FLIGHT)) / FLIGHT;
  if (u < 0 || u > 1.25) return null;
  const c = centre(target);
  const start = {x: c.x + 520 + (a.thumb ? 120 : -80), y: -260};
  const e = ease.inOut(clamp01(u));
  // Arc in from the top right, a touch of overshoot at the landing.
  const x = mix(start.x, c.x, e) + Math.sin(e * Math.PI) * -140;
  const y = mix(start.y, c.y, e * e * (3 - 2 * e));
  const size = target.w;
  const s = mix(1.35, 1, e);
  const rot = mix(16, 0, e);
  const fade = 1 - clamp01((u - 1) / 0.12);
  const ghosts = u < 1 ? [6, 5, 4, 3, 2, 1] : [];
  const draw = (key: string, gu: number, op: number) => {
    const ge = ease.inOut(clamp01(gu));
    const gx = mix(start.x, c.x, ge) + Math.sin(ge * Math.PI) * -140;
    const gy = mix(start.y, c.y, ge * ge * (3 - 2 * ge));
    return <div key={key} style={{position: "absolute", left: gx - size / 2, top: gy - size / 2, width: size, height: size, opacity: op,
      transform: `scale(${mix(1.35, 1, ge)}) rotate(${mix(16, 0, ge)}deg)`}}>
      <Img src={staticFile(`trailer-v3/${a.img}`)} style={{width: size, height: size, objectFit: "contain",
        filter: "drop-shadow(0 14px 22px #2b2f5540)"}}/>
    </div>;
  };
  return (
    <>
      {ghosts.map((g) => draw(`g${g}`, u - (g * 0.0042) / FLIGHT, 0.26 * (7 - g) / 6))}
      <div style={{position: "absolute", left: x - size / 2, top: y - size / 2, width: size, height: size, opacity: fade,
        transform: `scale(${s}) rotate(${rot}deg)`}}>
        <Img src={staticFile(`trailer-v3/${a.img}`)} style={{width: size, height: size, objectFit: "contain",
          filter: "drop-shadow(0 14px 22px #2b2f5540)"}}/>
      </div>
    </>
  );
};

/** Soft accent ring at each landing, on the beat. */
const Ripple: React.FC<{at: number; x: number; y: number; t: number}> = ({at, x, y, t}) => {
  const u = (t - at) / 0.55;
  if (u < 0 || u > 1) return null;
  const r = mix(60, 260, ease.out(u));
  return <div style={{position: "absolute", left: x - r, top: y - r, width: r * 2, height: r * 2, borderRadius: "50%",
    border: `${mix(10, 1, u)}px solid ${ACCENT}`, opacity: (1 - u) * 0.45, boxShadow: `0 0 40px ${ACCENT}55`}}/>;
};

export const AutoSort: React.FC = () => {
  const t = useTime();
  const cam = camAt(t, CAM);
  const native = remap(t, ANCHORS);
  return (
    <AbsoluteFill>
      <Stage cam={cam}>
        <Take src="auto" at={native}/>
        {ARRIVALS.map((a) => {
          const r = targets.auto.arrivals[a.name];
          return r ? <Ripple key={`r-${a.name}`} at={a.t} x={centre(r).x} y={centre(r).y} t={t}/> : null;
        })}
        {ARRIVALS.map((a) => <Incoming key={a.name} a={a} t={t}/>)}
      </Stage>
      <div style={{position: "absolute", left: 120, top: 112}}>
        <Words text="New files sort themselves." start={8.12} end={11.72}
          style={{font: `650 84px/1.08 ${FONT_DISPLAY}`, color: INK, letterSpacing: "-0.028em"}}/>
        <Fade start={8.6} end={11.72} style={{marginTop: 22, font: `450 34px/1.3 ${FONT_TEXT}`, color: INK_SOFT}}>
          Set a rule once. Every new file lands in its fence.
        </Fade>
      </div>
    </AbsoluteFill>
  );
};

