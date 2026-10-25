import React from "react";
import {AbsoluteFill} from "remotion";
import {camAt, CamKey, Stage, Take} from "../Stage";
import {targets} from "../targets";
import {clamp01, cues, ease, mix, prog, remap} from "../timing";
import {ACCENT, CORAL, Fade, FONT_DISPLAY, FONT_MONO, FONT_TEXT, INK, INK_SOFT, useTime, Words} from "../Type";
import {Glint} from "./Opening";

export const DROP = 20.0;
export const TINT = 22.0;

/**
 * ai.mp4 native events: Docs fence appears 4.783, autoHeight 5.917, rule apply 8.217,
 * fences swell from 10.73 and icons snap to 96 DIP at ~11.0, tint 13.2. Each is placed on its cue; static stretches absorb the rest.
 */
const ANCHORS: [number, number][] = [
  [17.92, 4.703], [18.3, 5.083],
  [18.42, 5.837], [18.95, 6.367],
  [19.32, 8.137], [19.66, 8.477],
  // Fences start to swell at 10.73 s; the icons snap to 96 DIP at ~11.0 s, which lands on the drop.
  [DROP - 0.3, 10.7], [DROP + 0.65, 11.65],
  [TINT - 0.08, 13.12], [TINT + 0.6, 13.8],
];

/** The exact commands the capture ran (--rect is the physical screen rectangle), with their JSON results summarised. */
const STEPS = [
  {t: 18.0, args: "fence create --title Docs --rect 1760,1200,800,345", result: "created fence Docs"},
  {t: 18.5, args: "fence set Docs autoHeight true", result: "autoHeight: true"},
  {t: 19.0, args: "rule add --name PDFs --ext pdf --to Docs --index 0", result: "rule PDFs → Docs"},
  {t: 19.4, args: "rule apply", result: "moved 4 files to Docs"},
  {t: DROP - 0.38, args: "fence set --all iconSize 96", result: "3 fences updated"},
  {t: TINT - 0.05, args: 'fence set --all tint "#E86A5C"', result: "3 fences updated"},
];

export const AGENT_CAM: CamKey[] = [
  {t: 15.75, cx: 1960, cy: 1060, z: 0.84, rx: 2, ry: -4},
  {t: 16.5, cx: 1900, cy: 1010, z: 0.69, rx: 0, ry: -1.5, e: ease.out},
  {t: 19.7, cx: 1900, cy: 1020, z: 0.7, ry: 0, e: ease.soft},
  // Every fence grows at the drop: pull back to hold them all, clear of the Store's top/bottom crop.
  {t: 20.75, cx: 1889, cy: 1185, z: 0.62, ry: 1.2, e: ease.out},
  {t: 22.6, cx: 1880, cy: 1180, z: 0.625, e: ease.soft},
  // The card leaves; the fences move right of the headline and drift closer.
  {t: 23.4, cx: 1760, cy: 1185, z: 0.64, ry: 0, e: ease.inOut},
  {t: 25.72, cx: 1740, cy: 1180, z: 0.67, ry: -1.5, e: ease.soft},
];

const Spinner: React.FC<{t: number}> = ({t}) => (
  <div style={{width: 18, height: 18, borderRadius: "50%", border: "2.5px solid #ffffff30", borderTopColor: "#9fb4ff",
    transform: `rotate(${t * 720}deg)`}}/>
);

const Check: React.FC<{p: number}> = ({p}) => (
  <svg width="20" height="20" viewBox="0 0 20 20" style={{transform: `scale(${mix(0.4, 1, ease.out(p))})`, opacity: clamp01(p * 2)}}>
    <circle cx="10" cy="10" r="10" fill="#3fbf87"/>
    <path d="M5.5 10.4l3 3 6-6.6" stroke="#fff" strokeWidth="2.2" fill="none" strokeLinecap="round" strokeLinejoin="round"
      pathLength={1} strokeDasharray="1" strokeDashoffset={1 - clamp01(p * 1.5)}/>
  </svg>
);

/** A coding agent's transcript: the request, then the pecofence-cli calls it makes. */
const AgentCard: React.FC<{t: number}> = ({t}) => {
  const enter = prog(t, 16.2, 0.7);
  const leave = prog(t, 22.75, 0.5, ease.in);
  const {text, typeStart, typeEnd} = cues.prompt;
  const typed = Math.floor(clamp01((t - typeStart) / (typeEnd - typeStart)) * text.length);
  const caretOn = t < cues.prompt.submit && Math.floor(t * 3) % 2 === 0;
  const doneP = prog(t, 22.25, 0.45);
  const pulse = Math.exp(-Math.max(0, t - DROP) / 0.25) * (t >= DROP ? 1 : 0);
  return (
    <div style={{position: "absolute", left: 92, top: 198, width: 740,
      transform: `translateX(${mix(-120, 0, enter) - leave * 260}px) scale(${1 + pulse * 0.012})`, opacity: clamp01(enter * 1.5) * (1 - leave),
      filter: leave > 0 ? `blur(${leave * 12}px)` : undefined,
      borderRadius: 30, padding: "26px 32px 28px", background: "linear-gradient(180deg, #171c33ee, #10142aee)",
      border: "1px solid #ffffff1f", boxShadow: `0 50px 120px #1d213a55, 0 0 0 1px #00000030, 0 0 ${pulse * 80}px ${ACCENT}${Math.round(pulse * 160).toString(16).padStart(2, "0")}`,
      backdropFilter: "blur(30px) saturate(1.4)", color: "#fff"}}>
      <div style={{display: "flex", alignItems: "center", gap: 12, font: `600 21px/1 ${FONT_TEXT}`, color: "#aeb9e6", letterSpacing: "0.02em"}}>
        <svg width="22" height="22" viewBox="0 0 24 24"><path d="M12 2l2.4 7.6L22 12l-7.6 2.4L12 22l-2.4-7.6L2 12l7.6-2.4z" fill="#9fb4ff"/></svg>
        YOUR AI AGENT
        <div style={{marginLeft: "auto", font: `500 18px/1 ${FONT_MONO}`, color: "#c5d1ff", padding: "7px 12px", borderRadius: 999,
          background: "#4768de40", border: "1px solid #6f8cff55"}}>pecofence-cli</div>
      </div>
      <div style={{marginTop: 22, font: `600 16px/1 ${FONT_TEXT}`, color: "#8390bb", letterSpacing: "0.08em"}}>YOU</div>
      <div style={{marginTop: 9, font: `450 30px/1.3 ${FONT_TEXT}`, color: "#fff", minHeight: 117}}>
        {text.slice(0, typed)}
        <span style={{display: "inline-block", width: 3, height: 34, marginLeft: 3, verticalAlign: "-6px", background: "#9fb4ff", opacity: caretOn ? 1 : 0}}/>
      </div>
      <div style={{height: 1, background: "#ffffff1a", margin: "16px 0 16px"}}/>
      <div style={{display: "flex", flexDirection: "column", gap: 9}}>
        {STEPS.map((s, i) => {
          const p = prog(t, s.t - 0.12, 0.35);
          if (p <= 0) return null;
          const running = t < s.t + 0.2;
          return (
            <div key={i} style={{opacity: clamp01(p * 1.5), transform: `translateY(${mix(14, 0, p)}px)`}}>
              <div style={{display: "flex", gap: 14, alignItems: "flex-start"}}>
                <div style={{marginTop: 3, width: 20, flex: "none"}}>{running ? <Spinner t={t}/> : <Check p={prog(t, s.t + 0.2, 0.3)}/>}</div>
                <div style={{font: `450 18.5px/1.34 ${FONT_MONO}`, color: "#e6ebff"}}>
                  <span style={{color: "#8fa8ff", whiteSpace: "nowrap"}}>pecofence-cli</span>{s.args.split(" ").map((tok, k) => <React.Fragment key={k}> <span style={{whiteSpace: "nowrap"}}>{tok}</span></React.Fragment>)}
                </div>
              </div>
              <div style={{marginLeft: 34, marginTop: 1, font: `450 16px/1.3 ${FONT_MONO}`, color: "#79d6a8",
                opacity: prog(t, s.t + 0.22, 0.3, ease.linear)}}>{s.result}</div>
            </div>
          );
        })}
      </div>
      {doneP > 0 && (
        <div style={{marginTop: 16, font: `450 23px/1.32 ${FONT_TEXT}`, color: "#fff", opacity: doneP, transform: `translateY(${mix(10, 0, doneP)}px)`}}>
          Done. Your PDFs are in Docs, the icons are bigger and every fence has a warm tint.
        </div>
      )}
    </div>
  );
};

export const Agent: React.FC = () => {
  const t = useTime();
  const native = remap(t, ANCHORS);
  const base = camAt(t, AGENT_CAM);
  // Drop: a short punch-in and settle, plus a few frames of shake.
  const d = t - DROP;
  const punch = d >= 0 ? Math.exp(-d / 0.18) : 0;
  const shake = d >= 0 && d < 0.35 ? Math.sin(d * 90) * (1 - d / 0.35) * 6 : 0;
  const cam = {...base, z: base.z * (1 + punch * 0.06), cx: base.cx + shake, cy: base.cy - shake * 0.6};
  const fencesNow = targets.ai.fences["15.0"] ?? {};
  const flash = d >= 0 ? Math.exp(-d / 0.12) : 0;
  const tintWash = prog(t, TINT, 0.9, ease.linear);
  return (
    <AbsoluteFill>
      <Stage cam={cam}>
        <Take src="ai" at={native}/>
        {Object.entries(fencesNow).map(([name, r]) => (
          <div key={name} style={{position: "absolute", left: r.x, top: r.y, width: r.w, height: r.h, borderRadius: 24, overflow: "hidden"}}>
            <Glint t={t} at={DROP + 0.28 + (r.x - 1700) / 4000} dur={0.7} strength={0.5}/>
            <Glint t={t} at={TINT + 0.05 + (r.x - 1700) / 5000} dur={0.9} strength={0.45}/>
          </div>
        ))}
      </Stage>
      {/* Warm wash as the tint lands. */}
      {tintWash > 0 && tintWash < 1 && (
        <AbsoluteFill style={{mixBlendMode: "soft-light", opacity: Math.sin(tintWash * Math.PI) * 0.55,
          background: `radial-gradient(ellipse 60% 70% at 72% 55%, ${CORAL}, transparent 70%)`}}/>
      )}
      <AbsoluteFill style={{mixBlendMode: "screen", opacity: flash * 0.75,
        background: "radial-gradient(ellipse 70% 80% at 68% 55%, #ffffff, #fff4ea88 40%, transparent 75%)"}}/>
      {d >= 0 && d < 0.6 && (
        <AbsoluteFill style={{mixBlendMode: "screen", opacity: (1 - d / 0.6) * 0.5,
          background: `radial-gradient(circle at 68% 52%, transparent ${mix(0, 55, ease.out(d / 0.6))}%, #fff8f0 ${mix(4, 62, ease.out(d / 0.6))}%, transparent ${mix(10, 72, ease.out(d / 0.6))}%)`}}/>
      )}
      <div style={{position: "absolute", left: 96, top: 118}}>
        <Words text="Or just ask your AI." start={16.05} end={22.7} dur={0.6}
          style={{font: `650 60px/1.05 ${FONT_DISPLAY}`, color: INK, letterSpacing: "-0.025em"}}/>
      </div>
      <AgentCard t={t}/>
      <div style={{position: "absolute", left: 110, top: 292, width: 800}}>
        {["Your desktop.", "Configured", "by your AI."].map((line, i) => (
          <Words key={line} text={line} start={23.0 + i * 0.22} end={25.35} accent={i === 2 ? [2] : []} accentColor="#d9574a"
            style={{font: `650 104px/1.04 ${FONT_DISPLAY}`, color: INK, letterSpacing: "-0.032em", marginTop: i ? 4 : 0}}/>
        ))}
        <Fade start={23.9} end={25.35} style={{marginTop: 34, font: `450 33px/1.38 ${FONT_TEXT}`, color: INK_SOFT, maxWidth: 700}}>
          pecofence-cli is built in, ready for Claude Code, Codex and Cursor.
        </Fade>
      </div>
    </AbsoluteFill>
  );
};
