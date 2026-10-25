import React from "react";
import {Audio} from "@remotion/media";
import {AbsoluteFill, random, staticFile, useCurrentFrame} from "remotion";
import {Agent} from "./scenes/Agent";
import {AutoSort} from "./scenes/AutoSort";
import {EndCard} from "./scenes/EndCard";
import {Opening} from "./scenes/Opening";
import {Tabs} from "./scenes/Tabs";
import {clamp01, ease, FPS, mix} from "./timing";

/**
 * PecoFence trailer v3 — 30 s, 1920 × 1080, 60 fps.
 * Every product pixel is a native capture (public/trailer-v3/*.mp4); the camera,
 * typography, flying file cues and light effects are editorial.
 */

type Layer = {
  from: number; to: number; node: React.ReactNode;
  /** Transition styling at time t (seconds). */
  style?: (t: number) => {transform?: string; opacity?: number; blurX?: number; blur?: number};
};

/** Whip pan: both shots sit side by side and travel together, blurred along the motion. */
const PAN_AT = 7.72;
const PAN_DUR = 0.4;
const pan = (t: number, out: boolean) => {
  const p = ease.inOut(clamp01((t - PAN_AT) / PAN_DUR));
  const x = out ? -p * 1920 : (1 - p) * 1920;
  return {transform: `translateX(${x}px)`, blurX: Math.sin(p * Math.PI) * 90};
};

const LAYERS: Layer[] = [
  {from: 0, to: PAN_AT + PAN_DUR + 0.02, node: <Opening/>, style: (t) => pan(t, true)},
  {from: PAN_AT, to: 12.1, node: <AutoSort/>, style: (t) => (t < 9 ? pan(t, false) : zoomOut(t, 11.72))},
  {from: 11.72, to: 16.25, node: <Tabs/>, style: (t) => (t < 13 ? zoomIn(t, 11.72) : defocusOut(t, 15.6))},
  {from: 15.72, to: 26.4, node: <Agent/>, style: (t) => ({opacity: ease.out(clamp01((t - 15.72) / 0.45)), blur: mix(16, 0, ease.out(clamp01((t - 15.72) / 0.5)))})},
  {from: 25.7, to: 30.01, node: <EndCard/>},
];

function zoomOut(t: number, at: number) {
  const p = ease.in(clamp01((t - at) / 0.32));
  return {transform: `scale(${mix(1, 1.35, p)})`, blur: p * 22, opacity: 1 - clamp01((p - 0.55) / 0.45)};
}
function zoomIn(t: number, at: number) {
  const p = 1 - ease.out(clamp01((t - at - 0.05) / 0.5));
  return {transform: `scale(${mix(1, 0.86, p)})`, blur: p * 18, opacity: 1 - clamp01((p - 0.6) / 0.4)};
}
function defocusOut(t: number, at: number) {
  const p = ease.inOut(clamp01((t - at) / 0.55));
  return {transform: `scale(${mix(1, 1.06, p)})`, blur: p * 26, opacity: 1 - clamp01((p - 0.45) / 0.55)};
}

/** Horizontal-only motion blur for whip pans (CSS blur() is isotropic). */
const BlurDefs: React.FC<{amounts: number[]}> = ({amounts}) => (
  <svg width="0" height="0" style={{position: "absolute"}}>
    {amounts.map((a, i) => (
      <filter key={i} id={`hblur-${i}`} x="-10%" y="0%" width="120%" height="100%">
        <feGaussianBlur stdDeviation={`${a} 0`}/>
      </filter>
    ))}
  </svg>
);

/** Fine animated grain + gentle vignette: keeps large flat gradients from banding and adds a filmic finish. */
const Finish: React.FC = () => {
  const frame = useCurrentFrame();
  const seed = Math.floor(frame / 2);
  return (
    <>
      <AbsoluteFill style={{pointerEvents: "none", mixBlendMode: "soft-light", opacity: 0.22}}>
        <svg width="1920" height="1080">
          <filter id="grain">
            <feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" seed={Math.floor(random(`g${seed}`) * 1000)} stitchTiles="stitch"/>
            <feColorMatrix type="saturate" values="0"/>
          </filter>
          <rect width="1920" height="1080" filter="url(#grain)"/>
        </svg>
      </AbsoluteFill>
      <AbsoluteFill style={{pointerEvents: "none", background: "radial-gradient(ellipse 85% 85% at 50% 50%, transparent 60%, #1b1d3a22 100%)"}}/>
    </>
  );
};

export const TrailerFilm: React.FC<{withAudio?: boolean}> = ({withAudio = false}) => {
  const frame = useCurrentFrame();
  const t = frame / FPS;
  const active = LAYERS.map((l) => ({l, s: l.style?.(t) ?? {}})).filter(({l}) => t >= l.from && t < l.to);
  return (
    <AbsoluteFill style={{background: "#f3eee9"}}>
      <BlurDefs amounts={active.map(({s}) => s.blurX ?? 0)}/>
      {active.map(({l, s}, i) => {
        const filters = [s.blurX ? `url(#hblur-${i})` : "", s.blur ? `blur(${s.blur}px)` : ""].filter(Boolean).join(" ");
        return (
          <AbsoluteFill key={l.from} style={{transform: s.transform, opacity: s.opacity, filter: filters || undefined}}>
            {l.node}
          </AbsoluteFill>
        );
      })}
      <Finish/>
      {/* The master WAV is muxed after rendering (scripts/finish-trailer.mjs); preview-only here. */}
      {withAudio && <Audio src={staticFile("trailer-v3/audio/final/soundtrack.m4a")}/>}
    </AbsoluteFill>
  );
};
