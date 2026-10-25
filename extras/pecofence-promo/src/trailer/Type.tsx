import React from "react";
import {useCurrentFrame} from "remotion";
import {clamp01, ease, FPS, mix} from "./timing";

export const FONT_DISPLAY = '"Segoe UI Variable Display", "Segoe UI Variable", "Segoe UI", sans-serif';
export const FONT_TEXT = '"Segoe UI Variable Text", "Segoe UI Variable", "Segoe UI", sans-serif';
export const FONT_MONO = '"Cascadia Code", "Cascadia Mono", Consolas, monospace';

export const INK = "#19243a";
export const INK_SOFT = "#566177";
export const ACCENT = "#4768de";
export const CORAL = "#E86A5C";

/** Current time in seconds (composition-relative). */
export const useTime = () => useCurrentFrame() / FPS;

type WordsProps = {
  text: string;
  /** Seconds: first word starts entering. */
  start: number;
  /** Seconds: exit begins (words leave upwards). */
  end?: number;
  stagger?: number;
  dur?: number;
  exitDur?: number;
  style?: React.CSSProperties;
  /** Words (by index) to colour with `accentColor`. */
  accent?: number[];
  accentColor?: string;
  /** Rise distance as a fraction of the line height. */
  rise?: number;
  blur?: number;
};

/**
 * Kinetic headline: each word rises out of its own mask, de-blurs and settles
 * with an expo-out; the exit is a quick shared lift-and-fade.
 */
export const Words: React.FC<WordsProps> = ({text, start, end, stagger = 0.055, dur = 0.7, exitDur = 0.32, style, accent = [], accentColor = ACCENT, rise = 1.05, blur = 14}) => {
  const t = useTime();
  const words = text.split(" ");
  const exit = end === undefined ? 0 : ease.in(clamp01((t - end) / exitDur));
  return (
    <div style={{display: "flex", flexWrap: "wrap", columnGap: "0.26em", ...style,
      transform: `translateY(${-exit * 0.35}em)`, opacity: 1 - exit}}>
      {words.map((w, i) => {
        const p = ease.out(clamp01((t - start - i * stagger) / dur));
        return (
          <span key={i} style={{display: "inline-block", overflow: "hidden", padding: "0.08em 0.02em 0.14em", margin: "-0.08em -0.02em -0.14em"}}>
            <span style={{
              display: "inline-block",
              transform: `translateY(${mix(rise, 0, p) * 100}%) rotate(${mix(4, 0, p)}deg)`,
              filter: p < 1 ? `blur(${mix(blur, 0, p)}px)` : undefined,
              opacity: clamp01(p * 1.6),
              color: accent.includes(i) ? accentColor : undefined,
            }}>{w}</span>
          </span>
        );
      })}
    </div>
  );
};

/** Simple fade/rise for secondary copy. */
export const Fade: React.FC<{start: number; end?: number; dy?: number; dur?: number; style?: React.CSSProperties; children: React.ReactNode}> = ({start, end, dy = 18, dur = 0.6, style, children}) => {
  const t = useTime();
  const p = ease.out(clamp01((t - start) / dur));
  const x = end === undefined ? 0 : ease.in(clamp01((t - end) / 0.3));
  return <div style={{...style, opacity: p * (1 - x), transform: `translateY(${mix(dy, 0, p) - x * 12}px)`,
    filter: p < 1 ? `blur(${mix(8, 0, p)}px)` : undefined}}>{children}</div>;
};

/** PecoFence mark (brackets + four tiles), as in the site and app icon. */
export const Mark: React.FC<{size: number; color?: string; draw?: number; tiles?: number}> = ({size, color = "#fff", draw = 1, tiles = 1}) => (
  <svg width={size} height={size} viewBox="0 0 64 64" fill="none" style={{display: "block"}}>
    <path d="M27 8H14a6 6 0 0 0-6 6v13M37 8h13a6 6 0 0 1 6 6v13M8 37v13a6 6 0 0 0 6 6h13M56 37v13a6 6 0 0 1-6 6H37"
      stroke={color} strokeWidth="6" strokeLinecap="round" pathLength={1} strokeDasharray="1" strokeDashoffset={1 - draw}/>
    {[[22, 22, 1], [35, 22, 0.65], [22, 35, 0.65], [35, 35, 1]].map(([x, y, o], i) => {
      const p = ease.out(clamp01(tiles * 4 - i));
      return <rect key={i} x={x} y={y} width="8" height="8" rx="2" fill={color} opacity={o * p}
        style={{transformOrigin: `${x + 4}px ${y + 4}px`, transform: `scale(${mix(0.2, 1, p)})`}}/>;
    })}
  </svg>
);

/** Rounded-square app icon (blue plate, white mark), matching the Store logo. */
export const AppIcon: React.FC<{size: number; draw?: number; tiles?: number}> = ({size, draw = 1, tiles = 1}) => (
  <div style={{width: size, height: size, borderRadius: size * 0.235, background: "linear-gradient(160deg, #5a7bf0 0%, #4768de 55%, #3d5bd0 100%)",
    boxShadow: `0 ${size * 0.12}px ${size * 0.35}px #3452bf55, inset 0 1px 0 #ffffff40`, display: "grid", placeItems: "center"}}>
    <Mark size={size * 0.62} draw={draw} tiles={tiles}/>
  </div>
);
