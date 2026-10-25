"""Measure landing targets for the 2026-09 trailer (v3) from the native 4K takes.

uv run --with numpy --with pillow --with opencv-python-headless python extras/pecofence-promo/scripts/measure-trailer-targets.py

Needs the shell icons/templates from extract-trailer-icons.ps1 (public/trailer-v3/icons and
.cache/promo2/icon-templates). Writes
  public/trailer-v3/targets.json          fence rects, item icon/label boxes, tab-strip boxes, change onsets
  public/trailer-v3/stills/*.png          full-resolution stills
  .cache/promo2/targets-check-<take>.png  overlays of every measured box for visual review
All coordinates are physical pixels of the 3840 x 2160 frame; rects are {x, y, w, h} with
x + w / y + h exclusive.

Method
  * Frames: ffmpeg -ss <t> (first frame with pts >= t), BT.709 limited -> full range RGB.
  * Fence rects: the priors (state config geometry x 2, or coarse reads for the AI take) are
    refined per edge from a luminance profile across the edge, averaged along the edge's middle
    span: the glass panel has a 1-2 px highlight stroke with a soft shadow outside it, so the
    outermost strong step (>= 50 % of the window's largest step) is the panel edge.
  * Items: each item's own shell image (icon at 128/192 px, or the shell thumbnail) is composited
    over the local glass colour and located with normalised cross-correlation inside the panel.
    Identical icons (folders, PDFs) are assigned in reading order, which must match the fence's
    name sort. Labels are the ink bounding box below the icon box inside the item's column.
"""
import json
import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[3]
PROMO = ROOT / "extras/pecofence-promo"
PUB = PROMO / "public/trailer-v3"
ICONS = PUB / "icons"
CACHE = ROOT / ".cache/promo2"
FRAMES = CACHE / "frames"
TPL = CACHE / "icon-templates"
RAW = PROMO / ".capture/trailer-v3-raw"
SCALE = 2.0  # 200 % display scaling: physical px = DIP * 2
LUMA = np.array([0.2126, 0.7152, 0.0722], np.float32)

STUDIES = ["Atelier study.png", "Form study.png", "Sol study.png", "Still study.png", "Terra study.png", "Tide study.png"]
PROJECTS = ["Archive", "Brand", "Campaign", "Creative brief.pdf", "Launch checklist.md", "Website"]
TODAY = ["Creative brief.pdf", "Launch checklist.md", "Meeting notes.txt"]
DESK_ALL = ["Assets.zip", "Contract.pdf", "Creative brief.pdf", "Invoice 0926.pdf", "Launch checklist.md",
            "Meeting notes.txt", "Project links.url", "Q3 report.pdf", "Still study.png", "Terra study.png"]
DESK_AFTER = [n for n in DESK_ALL if not n.endswith(".pdf")]
DOCS = ["Contract.pdf", "Creative brief.pdf", "Invoice 0926.pdf", "Q3 report.pdf"]
ARRIVALS = [("Form study.png", "Images", 5.767), ("Launch checklist.md", "Documents", 6.917),
            ("Sol study.png", "Images", 8.167), ("Q3 report.pdf", "Documents", 9.383)]


def sort_names(names):
    return sorted(names, key=str.casefold)


def state_rects(take):
    cfg = json.loads((RAW / f"{take}-state.json").read_text(encoding="utf-8-sig"))
    out = {}
    for f in cfg["layouts"][0]["fences"]:
        if f["rolledUp"] or f.get("tabHost"):
            continue
        g = f["geometry"]
        out[f["title"]] = tuple(int(round(v * SCALE)) for v in (g["x"], g["y"], g["w"], g["h"]))
    return out


# ---------------------------------------------------------------- snapshots to measure
def snapshots():
    ov, auto, tabs = state_rects("overview"), state_rects("auto"), state_rects("tabs")
    # AI take: x/y/w from the capture geometry (plate at 640,360), heights/widths from coarse reads
    # of the footage (autoHeight and iconSize change them); every edge is re-measured below.
    ai = {
        4.0: {"Desktop": (1760, 470, 800, 776), "Inspiration": (2590, 470, 600, 552)},
        7.0: {"Desktop": (1760, 470, 800, 776), "Inspiration": (2590, 470, 600, 552), "Docs": (1760, 1200, 800, 330)},
        9.5: {"Desktop": (1760, 470, 800, 552), "Inspiration": (2590, 470, 600, 552), "Docs": (1760, 1200, 800, 330)},
        12.5: {"Desktop": (1760, 470, 768, 680), "Inspiration": (2590, 470, 512, 968), "Docs": (1760, 1200, 768, 680)},
        15.0: {"Desktop": (1760, 470, 768, 680), "Inspiration": (2590, 470, 512, 968), "Docs": (1760, 1200, 768, 680)},
    }
    snaps = []
    for take in ("overview", "dark"):
        snaps.append(dict(take=take, t=4.0, fences=[
            dict(title="Projects", prior=ov["Projects"], icon=64, items=PROJECTS),
            dict(title="Inspiration", prior=ov["Inspiration"], icon=96, items=STUDIES),
            dict(title="Today", prior=ov["Today"], icon=64, items=TODAY)]))
    images, docs = ["Still study.png", "Terra study.png"], ["Creative brief.pdf", "Meeting notes.txt"]
    snaps.append(dict(take="auto", t=4.0, fences=[
        dict(title="Images", prior=auto["Images"], icon=96, items=list(images)),
        dict(title="Documents", prior=auto["Documents"], icon=64, items=list(docs))]))
    for name, fence, ev in ARRIVALS:
        (images if fence == "Images" else docs).append(name)
        snaps.append(dict(take="auto", t=round(ev + 0.6, 3), arrival=name, fences=[
            dict(title="Images", prior=auto["Images"], icon=96, items=sort_names(images)),
            dict(title="Documents", prior=auto["Documents"], icon=64, items=sort_names(docs))]))
    snaps.append(dict(take="auto", t=12.0, fences=[
        dict(title="Images", prior=auto["Images"], icon=96, items=sort_names(images)),
        dict(title="Documents", prior=auto["Documents"], icon=64, items=sort_names(docs))]))
    for t, rects in ai.items():
        icon = 96 if t > 10.8 else 64
        fences = []
        for title, prior in rects.items():
            items = {"Desktop": DESK_ALL if t < 8 else DESK_AFTER, "Inspiration": STUDIES,
                     "Docs": [] if t < 8 else DOCS}[title]
            f = dict(title=title, prior=prior, icon=icon, items=None if t == 7.0 else items)
            if t == 7.0 and title == "Desktop":
                f["occluded"] = {"bottom": "Docs"}  # Docs (created 4.8 s) covers Desktop's lower edge
            fences.append(f)
        snaps.append(dict(take="ai", t=t, fences=fences, absent=["Docs"] if t < 4.8 else []))
    snaps.append(dict(take="tabs", t=4.0, fences=[
        dict(title="Projects", prior=tabs["Projects"], icon=96, items=PROJECTS),
        dict(title="Inspiration", prior=(1950, 690, 1060, 800), icon=96, items=STUDIES)]))
    snaps.append(dict(take="tabs", t=8.0, tabstrip=["Projects", "Inspiration"], fences=[
        dict(title="Projects", prior=tabs["Projects"], icon=96, items=STUDIES, activeTab="Inspiration")]))
    return snaps


# ---------------------------------------------------------------- frames
def frame(take, t):
    FRAMES.mkdir(parents=True, exist_ok=True)
    p = FRAMES / f"{take}-{t:.3f}.png"
    if not p.exists():
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(PUB / f"{take}.mp4"), "-frames:v", "1",
                        "-vf", "scale=in_color_matrix=bt709:in_range=tv:out_range=pc,format=rgb24", str(p)], check=True)
    return p


def load(p):
    return np.asarray(Image.open(p).convert("RGB")).astype(np.float32)


def rect(x, y, w, h):
    return {"x": int(x), "y": int(y), "w": int(w), "h": int(h)}


# ---------------------------------------------------------------- fence edges
def edge(img, side, r, R=32):
    """Outermost strong RGB step across one edge of prior rect r (see module doc).

    RGB (not luminance) because a tinted panel can match its own shadow's brightness."""
    x, y, w, h = r
    if side in ("left", "right"):
        pos = x if side == "left" else x + w
        lo = pos - R
        P = img[int(y + 0.25 * h):int(y + 0.75 * h), lo - 1:pos + R + 1].mean(0)
    else:
        pos = y if side == "top" else y + h
        lo = pos - R
        span = (0.45, 0.9) if side == "top" else (0.12, 0.88)  # top: skip title text / tab strip
        P = img[lo - 1:pos + R + 1, int(x + span[0] * w):int(x + span[1] * w)].mean(1)
    D = np.linalg.norm(np.diff(P, axis=0), axis=1)  # D[i]: step between coordinate lo-1+i and lo+i
    idx = np.nonzero(D >= 0.5 * D.max())[0]
    i = idx.min() if side in ("left", "top") else idx.max()
    return lo + int(i), float(D.max())


def search_radius(f, others, side, R=32):
    """Shrink the edge window so it never reaches a neighbouring fence's facing edge."""
    x, y, w, h = f["prior"]
    for o in others:
        ox, oy, ow, oh = o["prior"]
        if side in ("left", "right") and (oy < y + h and y < oy + oh):
            gap = x - (ox + ow) if side == "left" else ox - (x + w)
        elif side in ("top", "bottom") and (ox < x + w and x < ox + ow):
            gap = y - (oy + oh) if side == "top" else oy - (y + h)
        else:
            continue
        if gap > -R:  # neighbour on this side (or overlapping it)
            R = min(R, max(6, gap // 2 - 1))
    return R


def measure_fence(img, f, others, carry):
    x, y, w, h = f["prior"]
    got, strength, radius = {}, {}, {}
    for side in ("left", "top", "right", "bottom"):
        if side in f.get("occluded", {}):
            continue
        radius[side] = search_radius(f, others, side)
        got[side], strength[side] = edge(img, side, (x, y, w, h), radius[side])
    left, top = got["left"], got["top"]
    right = got["right"]
    notes = []
    if "bottom" in got:
        bottom = got["bottom"]
    else:
        prev = carry.get(f["title"])
        bottom = prev["y"] + prev["h"]
        notes.append(f"bottom edge occluded by {f['occluded']['bottom']}; height carried from the previous snapshot")
    r = rect(left, top, right - left, bottom - top)
    dev = max(abs(left - x), abs(top - y), abs(right - x - w), abs(bottom - y - h))
    return r, {"edgeStep": {k: round(v, 1) for k, v in strength.items()}, "searchRadius": radius, "priorDelta": dev, "notes": notes}


# ---------------------------------------------------------------- items
def slug(s):
    return "".join(c if c.isalnum() else "-" for c in s.lower()).strip("-")


def template_key(name):
    if name.endswith(" study.png"):
        return "thumb-" + slug(name[:-4])
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return {"pdf": "pdf", "txt": "txt", "md": "md", "zip": "zip", "url": "url", "png": "png-generic", "": "folder"}[ext]


def deliverable_icon(name):
    k = template_key(name)
    return f"icons/{k}.png"


def label_text(name):
    return name[:-4] if name.endswith(".url") else name  # the shell never shows .url extensions


def match_template(region, key, S, glass):
    """Returns (comp, alpha, response, note). zip: 7-Zip only has a 48 px glyph; the fence draws it
    enlarged inside a faint tile, so the native glyph is searched over a range of scales."""
    if key != "zip":
        t = np.asarray(Image.open(TPL / f"{key}-{S}.png").convert("RGBA")).astype(np.float32)
        a = t[..., 3:4] / 255.0
        comp = (t[..., :3] * a + glass * (1 - a)).astype(np.float32)
        return comp, t[..., 3], cv2.matchTemplate(region, comp, cv2.TM_CCOEFF_NORMED), None
    g = np.asarray(Image.open(TPL / "zip-48.png").convert("RGBA"))
    ys, xs = np.nonzero(g[..., 3] > 128)
    g = g[ys.min():ys.max() + 1, xs.min():xs.max() + 1].astype(np.float32)
    best = None
    for k in np.arange(1.5, 3.21, 0.1):
        size = (int(round(g.shape[1] * k)), int(round(g.shape[0] * k)))
        t = cv2.resize(g, size, interpolation=cv2.INTER_NEAREST)
        a = t[..., 3:4] / 255.0
        comp = (t[..., :3] * a + glass * (1 - a)).astype(np.float32)
        res = cv2.matchTemplate(region, comp, cv2.TM_CCOEFF_NORMED)
        if best is None or res.max() > best[2].max():
            best = (comp, t[..., 3], res, f"7-Zip 48 px glyph found drawn at x{k:.1f} (icons/zip-48.png); icon box centred on it")
    return best


def find_items(img, L, fr, S, names, dark):
    """Locate every item's icon box; returns list of dicts in display order."""
    rx, ry, rw, rh = fr["x"] + 4, fr["y"] + 64, fr["w"] - 8, fr["h"] - 68
    region = img[ry:ry + rh, rx:rx + rw]
    glass = np.median(region.reshape(-1, 3), axis=0)
    groups = {}
    for n in names:
        groups.setdefault(template_key(n), []).append(n)
    found = {}
    for key, members in groups.items():
        comp, alpha, res, note = match_template(region, key, S, glass)
        th, tw = comp.shape[:2]
        sup = int(S * 0.6)
        pts = []
        for _ in members:
            _, mx, _, (px, py) = cv2.minMaxLoc(res)
            pts.append((px, py, mx))
            res[max(0, py - sup):py + sup + 1, max(0, px - sup):px + sup + 1] = -1
        pts = reading_order(pts, S / 2)
        ys, xs = np.nonzero(alpha > 8)
        vis = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
        for n, (px, py, score) in zip(members, pts):
            gx, gy = rx + px, ry + py
            if key.startswith("thumb-") or key == "zip":
                box = rect(round(gx + tw / 2 - S / 2), round(gy + th / 2 - S / 2), S, S)
                visible = rect(gx, gy, tw, th)
            else:
                box = rect(gx, gy, S, S)
                visible = rect(gx + vis[0], gy + vis[1], vis[2] - vis[0], vis[3] - vis[1])
            found[n] = dict(name=n, iconFile=deliverable_icon(n), iconBox=box, iconVisible=visible, score=round(float(score), 3))
            # "icon" = where the image itself sits: the thumbnail's own rect, else the shell icon's square
            found[n]["icon"] = visible if key.startswith("thumb-") else box
            if note:
                found[n]["note"] = note
    items = [found[n] for n in names]
    # the fence sorts by name: reading order of the boxes must reproduce that order
    order = [p[3] for p in reading_order([(i["iconBox"]["x"], i["iconBox"]["y"], 0, i["name"]) for i in items], S / 2)]
    ok = order == names
    labels(L, items, S, dark, fr)
    return items, ok


def reading_order(pts, tol):
    rows = []
    for p in sorted(pts, key=lambda p: p[1]):
        if rows and abs(p[1] - rows[-1][0][1]) < tol:
            rows[-1].append(p)
        else:
            rows.append([p])
    return [q for r in rows for q in sorted(r, key=lambda p: p[0])]


def labels(L, items, S, dark, fr):
    xs = sorted({i["iconBox"]["x"] for i in items})
    ys = sorted({i["iconBox"]["y"] for i in items})
    dx = [b - a for a, b in zip(xs, xs[1:]) if b - a > S / 2]
    dy = [b - a for a, b in zip(ys, ys[1:]) if b - a > S / 2]
    pitch = int(np.median(dx)) if dx else int(S * 1.5)
    below = min(104, (int(np.median(dy)) - S - 6) if dy else 104)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (11, 11))
    for it in items:
        b = it["iconBox"]
        cx = b["x"] + S / 2
        x0, x1 = int(cx - pitch / 2 + 3), int(cx + pitch / 2 - 3)
        y0, y1 = b["y"] + S + 2, min(b["y"] + S + below, fr["y"] + fr["h"] - 8)
        reg = L[y0 - 8:y1 + 8, x0 - 8:x1 + 8]
        # local glass background with the text strokes removed (opening for light text, closing for dark)
        bg = cv2.morphologyEx(reg, cv2.MORPH_OPEN if dark else cv2.MORPH_CLOSE, kernel)
        ink = ((reg - bg) > 38) if dark else ((bg - reg) > 38)
        ink = ink[8:-8, 8:-8]
        n, lab, stats, _ = cv2.connectedComponentsWithStats(ink.astype(np.uint8), connectivity=8)
        keep = [k for k in range(1, n) if stats[k, cv2.CC_STAT_AREA] >= 3]
        if not keep:
            it["label"] = None
            continue
        x_a = min(stats[k, 0] for k in keep); y_a = min(stats[k, 1] for k in keep)
        x_b = max(stats[k, 0] + stats[k, 2] for k in keep); y_b = max(stats[k, 1] + stats[k, 3] for k in keep)
        # caption line pitch is ~31 px at 200 %: one line is 20-26 px tall, two lines 50-57 px
        lines = max(1, int(round((y_b - y_a - 25) / 31)) + 1)
        it["label"] = rect(x0 + x_a, y0 + y_a, x_b - x_a, y_b - y_a)
        it["labelText"] = label_text(it["name"])
        it["labelLines"] = lines
    return pitch


# ---------------------------------------------------------------- tab strip
def ridge(P, lo, hi):
    P = np.asarray(P)
    best, arg = -1e9, None
    for i in range(max(lo, 3), min(hi, len(P) - 3)):
        s = P[i] - (P[i - 3] + P[i + 3]) / 2
        if s > best:
            best, arg = s, i
    return arg, best


def tabstrip(img, L, fr, titles):
    x0, y0 = fr["x"] + 8, fr["y"] + 4
    x1, y1 = fr["x"] + int(fr["w"] * 0.6), fr["y"] + 76
    reg, rgb = L[y0:y1, x0:x1], img[y0:y1, x0:x1]
    blue = (rgb[..., 2] - rgb[..., 0] > 60) & (rgb[..., 2] > 120)
    bg = np.percentile(reg, 90, axis=1, keepdims=True)
    ink = (reg < bg - 50) & ~cv2.dilate(blue.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    cols = ink.any(0)
    runs, start, gap = [], None, 0
    for i, c in enumerate(np.concatenate([cols, [False] * 30])):
        if c:
            if start is None:
                start = i
            gap, end = 0, i
        elif start is not None:
            gap += 1
            if gap >= 24:
                runs.append((start, end + 1)); start = None
    out = {}
    for title, (a, b) in zip(titles, runs):
        rows = np.nonzero(ink[:, a:b].any(1))[0]
        text = rect(x0 + a, y0 + rows.min(), b - a, rows.max() + 1 - rows.min())
        tx0, ty0, tx1, ty1 = text["x"], text["y"], text["x"] + text["w"], text["y"] + text["h"]
        # pill outline: 1-2 px bright ridge around the label
        # pill outline: vertical strokes looked for in the text rows beside the text; windows stay
        # clear of the panel's own edge stroke.
        hp = L[ty0 + 4:ty1 - 4].mean(0)
        lx, ls = ridge(hp, tx0 - 34, tx0 - 8)
        rxx, rs = ridge(hp, tx1 + 6, tx1 + 30)
        # the stroke is a top-left-lit gradient: read top/bottom just inside the left stroke
        vp = L[:, lx + 8:lx + 16].mean(1)
        ty, ts = ridge(vp, ty0 - 22, ty0 - 4)
        by, bs = ridge(vp, ty1 + 2, ty1 + 20)
        entry = {"label": text, "labelText": title}
        strength = {"left": ls, "top": ts, "right": rs, "bottom": bs}
        weak = [k for k, v in strength.items() if v < 2.0]
        if "left" in weak and "right" not in weak:
            lx = tx0 - (rxx - tx1)
        if "right" in weak and "left" not in weak:
            rxx = tx1 + (tx0 - lx)  # faint inactive pill: mirror the measured left padding
        if len(weak) <= 1 and not {"top", "bottom"} & set(weak):
            entry["tab"] = rect(lx, ty, rxx + 1 - lx, by + 1 - ty)
            if weak:
                entry["tabEstimatedEdges"] = weak
        else:
            entry["tab"] = None
        entry["tabRidge"] = {k: round(float(v), 1) for k, v in strength.items()}
        ub = blue[:, a:b]
        if ub.sum() > 20:
            yy, xx = np.nonzero(ub)
            entry["underline"] = rect(x0 + a + xx.min(), y0 + yy.min(), xx.max() + 1 - xx.min(), yy.max() + 1 - yy.min())
            entry["active"] = True
        else:
            entry["active"] = False
        out[title] = entry
    return out


# ---------------------------------------------------------------- change onsets
_GRAY = {}


def gray_frames(take, W=960, H=540):
    """All frames of a take at quarter resolution (gray) with their presentation times."""
    if take not in _GRAY:
        cmd = ["ffmpeg", "-v", "error", "-i", str(PUB / f"{take}.mp4"), "-vf", f"scale={W}:{H}:flags=area,format=gray",
               "-fps_mode", "passthrough", "-f", "rawvideo", "-"]
        pts = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "packet=pts_time", "-of", "csv=p=0",
                              str(PUB / f"{take}.mp4")], capture_output=True, text=True, check=True).stdout.split()
        times = np.array(sorted(float(p.strip(",")) for p in pts))
        data = subprocess.run(cmd, capture_output=True, check=True).stdout
        f = np.frombuffer(data, np.uint8).reshape(-1, H, W).astype(np.float32)
        assert len(f) == len(times), (take, len(f), len(times))
        _GRAY[take] = (times, f)
    return _GRAY[take]


def transition(take, region, t0, t1, floor=0.25):
    """Onset / settle of a visual change inside region between t0 (before) and t1 (after).

    firstChange: first frame that differs from the t0 frame beyond codec noise (0.25 / 255 mean);
    onset: first frame whose difference from the t0 frame exceeds 10 % of the total change;
    settled: first frame after which the difference from the t1 frame stays under 5 %."""
    times, f = gray_frames(take)
    x, y, w, h = region
    i0, i1 = int(np.searchsorted(times, t0)), int(np.searchsorted(times, t1))
    sl = f[i0:i1 + 1, y // 4:(y + h) // 4, x // 4:(x + w) // 4]
    d_ref = np.abs(sl - sl[0]).mean(axis=(1, 2))
    d_fin = np.abs(sl - sl[-1]).mean(axis=(1, 2))
    total = float(d_ref[-1])
    first = int(np.argmax(d_ref > floor))
    on = int(np.argmax(d_ref > max(0.1 * total, floor)))
    late = np.nonzero(d_fin > max(0.05 * total, floor))[0]
    st = int(late[-1] + 1) if len(late) else 0
    return {"firstChange": round(float(times[i0 + first]), 3), "onset": round(float(times[i0 + on]), 3),
            "settled": round(float(times[i0 + min(st, len(sl) - 1)]), 3), "change": round(total, 2)}


def onsets(take, regions, thr=0.6):
    """Per-region change bursts (frame-to-frame mean abs gray diff at quarter resolution, 8-bit units)."""
    times, f = gray_frames(take)
    out = {}
    for name, (x, y, w, h) in regions.items():
        sl = f[:, y // 4:(y + h) // 4, x // 4:(x + w) // 4]
        d = np.concatenate([[0], np.abs(np.diff(sl, axis=0)).mean(axis=(1, 2))])
        bursts, start, quiet = [], None, 0
        for i, v in enumerate(d):
            if v > thr:
                if start is None:
                    start = i
                last, quiet = i, 0
            elif start is not None:
                quiet += 1
                if quiet > 12:
                    bursts.append({"start": round(times[start], 3), "settled": round(times[last], 3),
                                   "peak": round(float(d[start:last + 1].max()), 2)})
                    start = None
        out[name] = bursts
    return out


# ---------------------------------------------------------------- overlays
def overlay(take, entries):
    tiles = []
    font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 15)
    for t, path, fences, extra in entries:
        im = Image.open(path).convert("RGB")
        k = 0.5
        im = im.resize((int(im.width * k), int(im.height * k)), Image.LANCZOS)
        d = ImageDraw.Draw(im)

        def box(r, col, w=1):
            if r:
                d.rectangle([r["x"] * k, r["y"] * k, (r["x"] + r["w"]) * k - 1, (r["y"] + r["h"]) * k - 1], outline=col, width=w)

        for f in fences:
            box(f["rect"], (255, 0, 200), 2)
            d.text((f["rect"]["x"] * k + 4, (f["rect"]["y"] + f["rect"]["h"]) * k + 2), f"{f['title']} {f['rect']}", font=font, fill=(200, 0, 160))
            for it in f.get("items") or []:
                box(it["icon"], (0, 170, 255))
                box(it["iconVisible"], (0, 200, 90))
                box(it.get("label"), (255, 140, 0))
        for r in extra:
            box(r, (255, 0, 0))
        d.text((12, 8), f"{take} t={t}", font=ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 28), fill=(220, 0, 0))
        tiles.append(im)
    cols = 1 if len(tiles) == 1 else 2
    rows = (len(tiles) + cols - 1) // cols
    W, H = tiles[0].size
    sheet = Image.new("RGB", (W * cols, H * rows), "white")
    for i, im in enumerate(tiles):
        sheet.paste(im, ((i % cols) * W, (i // cols) * H))
    sheet.save(CACHE / f"targets-check-{take}.png")


# ---------------------------------------------------------------- main
def main():
    out = {"version": 1,
           "frame": {"width": 3840, "height": 2160, "fps": 60, "units": "physical px (DIP x 2 at 200 % scaling)",
                     "rect": "{x, y, w, h}; x + w and y + h are exclusive"},
           "method": __doc__.split("Method", 1)[1].strip(),
           "legend": {"rect": "glass panel bounds (window rect; the soft shadow is outside it)",
                      "icon": "icon box: the square the shell icon image is drawn into (128 px for 64-DIP, 192 px for 96-DIP icons); "
                              "for image thumbnails it is the thumbnail's own rect (aspect-fit, full box height)",
                      "iconBox": "the square layout box (same as icon for type icons)",
                      "iconVisible": "tight box of the non-transparent pixels of the icon image",
                      "label": "tight ink box of the item's caption text",
                      "iconFile": "matching deliverable in public/trailer-v3/",
                      "fenceRects": "per take: {time: {fence title: rect | null (not on screen yet)}}",
                      "events": "measured visual change times (s, video time): firstChange / onset (10 %) / settled"},
           "notes": [
               "Portal fences sort by name only (folders are not grouped first): Projects = Archive, Brand, Campaign, "
               "Creative brief.pdf, Launch checklist.md, Website. Virtual fences (auto take) re-sort on arrival, so "
               "existing items shift right when a name sorts before them.",
               "Icon boxes are 128 px (64 DIP) or 192 px (96 DIP); thumbnails are aspect-fit 103x128 / 155x192.",
               "ai t=7.0: Docs (created ~4.8 s) overlaps the lower part of Desktop; Desktop's bottom edge is hidden, "
               "its height is carried from t=4.0 (layout unchanged until the PDFs move at ~8.2 s).",
               "ai: Docs is not on screen at t=4.0 (fenceRects value null).",
               "Assets.zip: 7-Zip has no large icon; the fence draws its 48 px glyph (icons/zip-48.png) at 2x inside a "
               "faint tile, which differs from icons/zip.png (shell 256 px: small glyph in a large tile).",
               "Frames are the first frame with pts >= t (the takes are variable frame rate at 60 fps nominal)."],
           "takes": {}}
    carry, checks = {}, {}
    for snap in snapshots():
        take, t = snap["take"], snap["t"]
        path = frame(take, t)
        img = load(path)
        L = img @ LUMA
        dark = take == "dark"
        fences = []
        for f in snap["fences"]:
            r, info = measure_fence(img, f, [o for o in snap["fences"] if o is not f], carry.get(take, {}))
            carry.setdefault(take, {})[f["title"]] = r
            entry = {"title": f["title"], "rect": r, "iconSizeDip": f["icon"], "iconBoxPx": int(f["icon"] * SCALE)}
            if f.get("activeTab"):
                entry["tabs"] = snap.get("tabstrip")
                entry["activeTab"] = f["activeTab"]
            entry["measure"] = info
            if f.get("items") is not None:
                S = int(f["icon"] * SCALE)
                items, ok = find_items(img, L, r, S, f["items"], dark)
                for it in items:
                    it["fence"] = f["title"]
                entry["items"] = [{k: it[k] for k in ("fence", "name", "iconFile", "icon", "iconBox", "iconVisible", "label",
                                                        "labelText", "labelLines", "score", "note") if k in it} for it in items]
                entry["orderMatchesNameSort"] = ok
                low = [it["name"] for it in items if it["score"] < 0.85]
                if not ok or low:
                    print(f"  !! {take} {t} {f['title']}: order ok={ok} low-score={low}")
            fences.append(entry)
        extra = []
        snapout = {"t": t, "frame": str(path.relative_to(ROOT)).replace("\\", "/"), "fences": fences}
        if snap.get("absent"):
            snapout["absent"] = snap["absent"]
        if snap.get("tabstrip"):
            ts = tabstrip(img, L, fences[0]["rect"], snap["tabstrip"])
            snapout["tabStrip"] = ts
            for v in ts.values():
                extra += [v["label"], v.get("tab"), v.get("underline")]
        if snap.get("arrival"):
            snapout["arrival"] = snap["arrival"]
        out["takes"].setdefault(take, {"video": f"trailer-v3/{take}.mp4", "snapshots": []})["snapshots"].append(snapout)
        checks.setdefault(take, []).append((t, path, fences, extra))
        print(take, t, " | ".join(f"{f['title']} {tuple(f['rect'].values())} d{f['measure']['priorDelta']}" for f in fences))

    # convenience views ---------------------------------------------------------------
    auto = out["takes"]["auto"]
    arr = []
    for name, fence, ev in ARRIVALS:
        s = next(s for s in auto["snapshots"] if s.get("arrival") == name)
        f = next(f for f in s["fences"] if f["title"] == fence)
        it = next(i for i in f["items"] if i["name"] == name)
        arr.append({"name": name, "fence": fence, "event": ev, "t": s["t"], **{k: it[k] for k in ("iconFile", "icon", "iconBox", "iconVisible", "label")}})
    auto["arrivals"] = arr
    for a in arr:
        cell = a["iconBox"]
        region = (cell["x"] - 40, cell["y"] - 10, cell["w"] + 80, cell["h"] + 110)
        a["appearance"] = transition("auto", region, a["event"] - 0.4, a["event"] + 1.2)
    ai = out["takes"]["ai"]
    ai["events"] = []
    for what, region, t0, t1 in [
            ("Docs fence appears (fence create)", (1760, 1200, 800, 345), 4.2, 5.6),
            ("Docs autoHeight (345 -> 330 px)", (1760, 1480, 800, 80), 5.6, 7.0),
            ("PDFs move Desktop -> Docs (rule apply)", (1760, 470, 800, 1060), 7.6, 9.4),
            ("icons 64 -> 96 DIP (fences re-flow)", (1760, 470, 1440, 1420), 10.2, 12.4),
            ("tint #E86A5C", (1760, 470, 1440, 1420), 12.7, 14.6)]:
        ai["events"].append({"what": what, "region": rect(*region), **transition("ai", region, t0, t1)})
    tb = out["takes"]["tabs"]
    tb["events"] = []
    for what, region, t0, t1 in [("Inspiration docks into Projects (merge)", (830, 690, 2180, 800), 6.0, 7.6),
                                 ("activate Projects", (830, 690, 1060, 800), 9.0, 10.6),
                                 ("activate Inspiration", (830, 690, 1060, 800), 11.5, 13.1),
                                 ("activate Projects", (830, 690, 1060, 800), 14.0, 15.6)]:
        tb["events"].append({"what": what, "region": rect(*region), **transition("tabs", region, t0, t1)})
    for take in ("overview", "dark"):
        out["takes"][take]["events"] = [{"what": "fences appear", "region": rect(640, 360, 2560, 1440),
                                         **transition(take, (640, 360, 2560, 1440), 2.0, 3.4)}]
    for take, regions in {"auto": {"Images": (840, 780, 1260, 640), "Documents": (2200, 800, 800, 600)},
                          "ai": {"Desktop": (1760, 470, 800, 776), "Inspiration": (2590, 470, 600, 970), "Docs": (1760, 1200, 800, 700)},
                          "tabs": {"left": (830, 690, 1060, 800), "right": (1950, 690, 1060, 800)},
                          "overview": {"plate": (640, 360, 2560, 1440)}, "dark": {"plate": (640, 360, 2560, 1440)}}.items():
        out["takes"][take]["changeBursts"] = onsets(take, regions)
        print(take, "bursts", json.dumps(out["takes"][take]["changeBursts"]))
    for take, v in out["takes"].items():
        v["fenceRects"] = {}
        for snap in v["snapshots"]:
            rects = {f["title"]: f["rect"] for f in snap["fences"]}
            rects.update({a: None for a in snap.get("absent", [])})
            v["fenceRects"][f"{snap['t']}"] = rects
    (PUB / "targets.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    for take, entries in checks.items():
        overlay(take, entries)

    # stills --------------------------------------------------------------------------
    stills = PUB / "stills"
    stills.mkdir(parents=True, exist_ok=True)
    for take, t, name in [("overview", 4.0, "overview-4s"), ("dark", 4.0, "dark-4s"), ("ai", 3.0, "ai-3s"),
                          ("ai", 15.0, "ai-15s"), ("auto", 12.0, "auto-12s"), ("tabs", 8.0, "tabs-8s")]:
        shutil.copy2(frame(take, t), stills / f"{name}.png")
    print("wrote", PUB / "targets.json")


if __name__ == "__main__":
    main()
