import React from "react";
import {AbsoluteFill} from "remotion";
import {camAt, Stage, Take} from "../Stage";
import {clamp01, ease, mix, prog} from "../timing";
import {AppIcon, Fade, FONT_DISPLAY, FONT_TEXT, INK, INK_SOFT, useTime, Words} from "../Type";
import {AGENT_CAM} from "./Agent";

const START = 25.7;

/** Windows logo-free "Microsoft Store" and site buttons, drawn as simple pills. */
const Pill: React.FC<{children: React.ReactNode; strong?: boolean}> = ({children, strong}) => (
  <div style={{display: "flex", alignItems: "center", gap: 14, padding: "22px 36px", borderRadius: 999,
    font: `600 36px/1 ${FONT_TEXT}`, color: strong ? "#fff" : INK,
    background: strong ? "linear-gradient(180deg, #5776ea, #4263d8)" : "#ffffffb8",
    border: strong ? "1px solid #ffffff40" : "1px solid #19243a1a",
    boxShadow: strong ? "0 14px 34px #3452bf40, inset 0 1px 0 #ffffff45" : "0 10px 30px #19243a14"}}>
    {children}
  </div>
);

const StoreGlyph = () => (
  <svg width="36" height="36" viewBox="0 0 24 24" fill="none">
    <path d="M4 8h16l-1.2 11.2a2 2 0 0 1-2 1.8H7.2a2 2 0 0 1-2-1.8z" fill="#fff" opacity=".95"/>
    <path d="M8.5 8V6.5a3.5 3.5 0 0 1 7 0V8" stroke="#fff" strokeWidth="1.8"/>
  </svg>
);

export const EndCard: React.FC = () => {
  const t = useTime();
  // Continue the AI shot's camera, then push through it into a soft, bright backdrop.
  const base = camAt(Math.min(t, 25.72), AGENT_CAM);
  const push = prog(t, START, 0.8, ease.inOut);
  const drift = prog(t, 26.5, 3.5, ease.soft);
  const cam = {...base, z: base.z * mix(1, 1.38, push) * mix(1, 1.05, drift), cx: base.cx + push * 260, cy: base.cy - push * 30};
  const blur = mix(0, 34, push);
  const veil = prog(t, START + 0.1, 0.65, ease.inOut);
  const iconP = prog(t, 26.25, 0.9);
  const iconSpring = iconP < 1 ? mix(0.55, 1, iconP) + Math.sin(iconP * Math.PI) * 0.06 : 1;
  return (
    <AbsoluteFill>
      <Stage cam={cam} style={{filter: `blur(${blur}px) saturate(${mix(1, 1.15, push)})`}}>
        <Take src="ai" at={16.8}/>
      </Stage>
      <AbsoluteFill style={{background: "radial-gradient(ellipse 62% 58% at 50% 50%, #fbf7f2f2 0%, #f8f2ecc8 42%, #f3e9ea70 78%, #efe3e650 100%)", opacity: veil}}/>
      <AbsoluteFill style={{alignItems: "center", justifyContent: "center", flexDirection: "column"}}>
        <div style={{opacity: clamp01(iconP * 2), transform: `translateY(${mix(40, 0, iconP)}px) scale(${iconSpring})`}}>
          <AppIcon size={210} draw={prog(t, 26.35, 0.7)} tiles={prog(t, 26.6, 0.6, ease.linear)}/>
        </div>
        <div style={{marginTop: 44}}>
          <Words text="PecoFence" start={26.45} dur={0.8}
            style={{font: `650 150px/1 ${FONT_DISPLAY}`, color: INK, letterSpacing: "-0.035em", justifyContent: "center"}}/>
        </div>
        <Fade start={26.9} style={{marginTop: 28, font: `500 46px/1.2 ${FONT_DISPLAY}`, color: INK_SOFT, letterSpacing: "-0.01em"}}>
          Free and open source for Windows 11
        </Fade>
        <Fade start={27.3} style={{marginTop: 60, display: "flex", gap: 26}}>
          <Pill strong><StoreGlyph/>Microsoft Store</Pill>
          <Pill>pecofence.jiang.jp</Pill>
        </Fade>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
