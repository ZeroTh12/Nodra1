import React from "react";
import {AbsoluteFill} from "remotion";
import {camAt, CamKey, Stage, Take} from "../Stage";
import {centre, targets} from "../targets";
import {ease, mix, remap} from "../timing";
import {ACCENT, Fade, FONT_DISPLAY, FONT_TEXT, INK, INK_SOFT, useTime, Words} from "../Type";

/** tabs.mp4: merge at 6.55 s, tab switches at 9.55 s and 12.033 s (measured onsets) → 12.5 / 14.0 / 15.0 on the timeline. */
const MERGE = 12.5;
const CLICKS = [
  {t: 14.0, native: 9.55, tab: "Projects"},
  {t: 15.0, native: 12.033, tab: "Inspiration"},
];
const ANCHORS: [number, number][] = [
  [MERGE - 0.1, 6.45], [MERGE + 0.6, 7.15],
  ...CLICKS.flatMap((c) => [[c.t - 0.06, c.native - 0.06], [c.t + 0.5, c.native + 0.5]] as [number, number][]),
];

const merged = targets.tabs.merged;
const mc = centre(merged);
const CAM: CamKey[] = [
  {t: 11.7, cx: 1920, cy: 1180, z: 0.66, rx: 4},
  {t: 12.15, cx: 1920, cy: 1110, z: 0.72, rx: 1, e: ease.out},
  {t: 12.62, z: 0.725},
  // After the merge the camera settles on the tabbed fence, leaving the right side for the title.
  {t: 13.3, cx: mc.x + 330 / 0.95, cy: mc.y + 20, z: 0.95, rx: 0, ry: 2, e: ease.inOut},
  {t: 16.1, cx: mc.x + 320 / 1.0, cy: mc.y + 10, z: 1.0, ry: -1, e: ease.soft},
];

const Tap: React.FC<{t: number; at: number; x: number; y: number}> = ({t, at, x, y}) => {
  const u = (t - at + 0.08) / 0.6;
  if (u < 0 || u > 1) return null;
  const r = mix(18, 120, ease.out(u));
  return (
    <>
      <div style={{position: "absolute", left: x - r, top: y - r, width: r * 2, height: r * 2, borderRadius: "50%",
        background: `radial-gradient(circle, ${ACCENT}55 0%, ${ACCENT}22 55%, transparent 70%)`, opacity: 1 - u}}/>
      <div style={{position: "absolute", left: x - r, top: y - r, width: r * 2, height: r * 2, borderRadius: "50%",
        border: `3px solid ${ACCENT}`, opacity: (1 - u) * 0.6}}/>
    </>
  );
};

export const Tabs: React.FC = () => {
  const t = useTime();
  const cam = camAt(t, CAM);
  const native = remap(t, ANCHORS);
  return (
    <AbsoluteFill>
      <Stage cam={cam}>
        <Take src="tabs" at={native}/>
        {CLICKS.map((c) => {
          const r = targets.tabs.tabLabels[c.tab];
          return r ? <Tap key={c.tab} t={t} at={c.t} x={centre(r).x} y={centre(r).y}/> : null;
        })}
      </Stage>
      <div style={{position: "absolute", left: 1140, top: 350, width: 700}}>
        <Words text="One fence." start={12.85} end={15.72}
          style={{font: `650 96px/1.05 ${FONT_DISPLAY}`, color: INK, letterSpacing: "-0.03em"}}/>
        <Words text="Every project." start={13.1} end={15.72} accent={[1]}
          style={{font: `650 96px/1.05 ${FONT_DISPLAY}`, color: INK, letterSpacing: "-0.03em", marginTop: 6}}/>
        <Fade start={13.55} end={15.72} style={{marginTop: 30, font: `450 34px/1.35 ${FONT_TEXT}`, color: INK_SOFT, maxWidth: 620}}>
          Merge fences into tabs and switch in a click.
        </Fade>
      </div>
    </AbsoluteFill>
  );
};
