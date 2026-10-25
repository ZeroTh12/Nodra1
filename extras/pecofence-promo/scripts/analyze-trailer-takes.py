"""Frame-difference onsets for the trailer takes (v3).

uv run --with numpy python extras/pecofence-promo/scripts/analyze-trailer-takes.py
Writes .capture/trailer-v3-raw/<take>-motion.json: per-frame mean change inside the
plate and detected change segments, used to align edits with the native events.
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

RAW = Path(__file__).resolve().parents[1] / ".capture/trailer-v3-raw"
W, H = 480, 270


def frames(path):
    cmd = ["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"scale={W}:{H}:flags=area,format=gray", "-f", "rawvideo", "-"]
    data = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(data, np.uint8).reshape(-1, H, W).astype(np.float32)


def main(takes):
    for take in takes:
        f = frames(RAW / f"{take}.mkv")
        diff = np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))
        diff = np.concatenate([[0.0], diff])
        active = diff > 0.05
        segments, start = [], None
        for i, a in enumerate(active):
            if a and start is None:
                start = i
            if not a and start is not None:
                if i - start >= 1:
                    segments.append({"start": start, "end": i, "t": round(start / 60, 3), "dur": round((i - start) / 60, 3),
                                     "peak": round(float(diff[start:i].max()), 3)})
                start = None
        # merge segments separated by < 6 frames
        merged = []
        for s in segments:
            if merged and s["start"] - merged[-1]["end"] < 6:
                m = merged[-1]
                m["end"] = s["end"]; m["dur"] = round((m["end"] - m["start"]) / 60, 3); m["peak"] = max(m["peak"], s["peak"])
            else:
                merged.append(dict(s))
        out = {"take": take, "fps": 60, "frames": int(len(f)), "segments": merged,
               "diff": [round(float(x), 3) for x in diff]}
        (RAW / f"{take}-motion.json").write_text(json.dumps(out), encoding="utf-8")
        print(take, len(f), "frames")
        for s in merged:
            print(f"  {s['t']:7.3f}s  f{s['start']:5d}-{s['end']:5d}  dur {s['dur']:.3f}  peak {s['peak']}")


if __name__ == "__main__":
    main(sys.argv[1:] or ["overview", "dark", "auto", "tabs", "ai"])
