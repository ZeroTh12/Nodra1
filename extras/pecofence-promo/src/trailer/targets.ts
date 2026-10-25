import type {Rect} from "./Stage";
import raw from "./targets.json";

/** Geometry measured on the native takes (3840 × 2160 physical px); see scripts/make-trailer-targets.py. */
export type Item = {fence: string; name: string; icon: Rect};
export type Targets = {
  overview: {fences: Record<string, Rect>; items: Item[]};
  auto: {fences: Record<string, Rect>; arrivals: Record<string, Rect>};
  tabs: {before: Record<string, Rect>; merged: Rect; tabLabels: Record<string, Rect>};
  ai: {fences: Record<string, Record<string, Rect>>};
};

export const targets = raw as unknown as Targets;

export const centre = (r: Rect) => ({x: r.x + r.w / 2, y: r.y + r.h / 2});
