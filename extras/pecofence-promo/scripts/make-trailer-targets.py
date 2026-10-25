"""Compacts public/trailer-v3/targets.json (measured on the native takes) into src/trailer/targets.json.

uv run python extras/pecofence-promo/scripts/make-trailer-targets.py
"""
import json
from pathlib import Path

PROMO = Path(__file__).resolve().parents[1]
src = json.loads((PROMO / "public/trailer-v3/targets.json").read_text(encoding="utf-8"))["takes"]


def snap(take, t):
    return next(s for s in src[take]["snapshots"] if abs(s["t"] - t) < 1e-6)


def fences(s):
    return {f["title"]: f["rect"] for f in s["fences"]}


ov = snap("overview", 4.0)
out = {
    "overview": {
        "fences": fences(ov),
        # iconBox: the square the shell draws into; the flying desktop icons use the same aspect-fit box.
        "items": [{"fence": it["fence"], "name": it["name"], "icon": it["iconBox"]} for f in ov["fences"] for it in f["items"]],
    },
    "auto": {
        "fences": fences(snap("auto", 4.0)),
        "arrivals": {a["name"]: a["iconBox"] for a in src["auto"]["arrivals"]},
    },
    "tabs": {
        "before": fences(snap("tabs", 4.0)),
        "merged": fences(snap("tabs", 8.0))["Projects"],
        # Tab chips measured by hand on stills/tabs-8s.png (2x crop of the title row).
        "tabLabels": {"Projects": {"x": 847, "y": 699, "w": 161, "h": 55}, "Inspiration": {"x": 1017, "y": 699, "w": 203, "h": 55}},
    },
    "ai": {"fences": {f'{s["t"]:.1f}': fences(s) for s in src["ai"]["snapshots"]}},
}
(PROMO / "src/trailer/targets.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print(len(out["overview"]["items"]), "overview items;", list(out["auto"]["arrivals"]), list(out["ai"]["fences"]))
