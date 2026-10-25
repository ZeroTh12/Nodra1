import {Easing} from "remotion";
import cues from "./cues.json";

export {cues};

/** 60 fps master; the Store copy is decimated to 30 fps at export. */
export const FPS = 60;
export const DURATION = Math.round(cues.duration * FPS);
/** Seconds → frame. */
export const f = (s: number) => Math.round(s * FPS);

export type Ease = (x: number) => number;
export const ease = {
  /** Expo-out: fast start, long settle. Used for most entrances. */
  out: Easing.bezier(0.16, 1, 0.3, 1),
  /** Symmetric camera moves. */
  inOut: Easing.bezier(0.65, 0, 0.35, 1),
  /** Gentle ease for slow drifts. */
  soft: Easing.bezier(0.45, 0, 0.2, 1),
  /** Accelerating exits. */
  in: Easing.bezier(0.7, 0, 0.84, 0),
  linear: (x: number) => x,
};

export const clamp01 = (x: number) => Math.min(1, Math.max(0, x));
export const mix = (a: number, b: number, t: number) => a + (b - a) * t;

/** 0 → 1 progress of `t` through [start, start + dur], eased. */
export const prog = (t: number, start: number, dur: number, e: Ease = ease.out) =>
  e(clamp01((t - start) / dur));

/** Piecewise-linear time remap: anchors are [timelineSeconds, sourceSeconds]. */
export const remap = (t: number, anchors: readonly (readonly [number, number])[]) => {
  if (t <= anchors[0][0]) return anchors[0][1] + (t - anchors[0][0]);
  for (let i = 1; i < anchors.length; i++) {
    const [t0, s0] = anchors[i - 1];
    const [t1, s1] = anchors[i];
    if (t <= t1) return s0 + ((t - t0) / (t1 - t0)) * (s1 - s0);
  }
  const [tl, sl] = anchors[anchors.length - 1];
  return sl + (t - tl);
};

/**
 * Native events play at real speed: each [timeline, source] event keeps `lead` seconds
 * before and `tail` seconds after at 1:1, and the static gaps between them absorb the
 * difference. Nothing moves in the gaps, so the retime is invisible.
 */
export const eventAnchors = (
  events: readonly (readonly [number, number])[],
  lead = 0.08,
  tail = 0.6,
): [number, number][] => {
  const out: [number, number][] = [];
  for (const [t, s] of events) {
    out.push([t - lead, s - lead], [t + tail, s + tail]);
  }
  return out;
};
