"""Original "messy desktop" thumbnails for the 2026-09 trailer (v3) intro.

uv run --with pillow --with numpy python extras/pecofence-promo/scripts/make-trailer-clutter.py

Everything is drawn procedurally (no stock, no screenshots, no third-party UI or logos):
4 abstract app "screenshots", 2 photo-like procedural landscapes, 2 paper documents.
Drawn at 2x and downsampled; 512 px on the long side. Writes public/trailer-v3/clutter/.
"""
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path(__file__).resolve().parents[1] / "public/trailer-v3/clutter"
FONTS = Path("C:/Windows/Fonts")
S = 2  # supersampling factor
rng = np.random.default_rng(926)

INK = (58, 60, 78)
MUTED = (160, 163, 180)
LINE = (224, 225, 234)
PAPER = (252, 251, 249)
SOFT = {"lavender": (196, 190, 232), "peach": (244, 196, 168), "mint": (170, 214, 192), "sky": (170, 204, 236),
        "butter": (245, 226, 160), "rose": (240, 184, 196), "teal": (96, 164, 170), "indigo": (112, 110, 176)}


def font(name, size):
    return ImageFont.truetype(str(FONTS / name), size * S)


def finish(img, name, size):
    img = img.resize(size, Image.LANCZOS)
    OUT.mkdir(parents=True, exist_ok=True)
    img.save(OUT / name, optimize=True)
    print(name, img.size, img.mode)


def grain(img, amount=4.0):
    a = np.asarray(img).astype(np.float32)
    n = rng.normal(0, amount, a.shape[:2])[..., None]
    a[..., :3] = np.clip(a[..., :3] + n, 0, 255)
    return Image.fromarray(a.astype(np.uint8), img.mode)


def rr(d, box, r, **kw):
    d.rounded_rectangle([v * S for v in box], radius=r * S, **kw)


def bar(d, x, y, w, h=6, fill=LINE):
    rr(d, (x, y, x + w, y + h), h / 2, fill=fill)


def text_lines(d, x, y, width, rows, gap=14, h=6, fill=LINE, seed=0):
    r = np.random.default_rng(seed)
    for i in range(rows):
        w = width * (0.55 + 0.45 * r.random()) if i % 4 != 3 else width * (0.25 + 0.3 * r.random())
        bar(d, x, y + i * gap, w, h, fill)


def window(size, title_w=120, accent=SOFT["indigo"], bg=(247, 247, 251)):
    """Generic window: rounded panel, neutral title bar, caption glyphs (no logos)."""
    W, H = size
    img = Image.new("RGB", (W * S, H * S), bg)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W * S, 30 * S], fill=(238, 238, 245))
    rr(d, (12, 9, 24, 21), 3, fill=accent)
    bar(d, 32, 12, title_w, 6, (198, 200, 214))
    cx = W - 16
    # close X, maximise box, minimise dash
    d.line([((cx - 4) * S, 11 * S), ((cx + 4) * S, 19 * S)], fill=(120, 122, 138), width=S)
    d.line([((cx - 4) * S, 19 * S), ((cx + 4) * S, 11 * S)], fill=(120, 122, 138), width=S)
    d.rectangle([(cx - 40) * S, 11 * S, (cx - 32) * S, 19 * S], outline=(120, 122, 138), width=S)
    d.line([((cx - 72) * S, 15 * S), ((cx - 64) * S, 15 * S)], fill=(120, 122, 138), width=S)
    return img, d


def shot_docs():
    W, H = 512, 320
    img, d = window((W, H), 110, SOFT["sky"])
    d.rectangle([0, 30 * S, W * S, 58 * S], fill=(244, 244, 249))
    for i in range(9):
        rr(d, (12 + i * 26, 37, 30 + i * 26, 51), 4, fill=(226, 227, 238) if i != 3 else SOFT["sky"])
    d.line([(0, 58 * S), (W * S, 58 * S)], fill=LINE, width=S)
    # sidebar outline
    d.rectangle([0, 59 * S, 120 * S, H * S], fill=(242, 242, 248))
    for i in range(8):
        y = 74 + i * 24
        if i == 2:
            rr(d, (8, y - 7, 112, y + 13), 5, fill=(226, 230, 246))
        d.ellipse([16 * S, y * S, 24 * S, (y + 8) * S], fill=list(SOFT.values())[i % 8])
        bar(d, 32, y + 1, 50 + (i * 17) % 40, 6, (204, 206, 220))
    # page
    rr(d, (144, 72, 488, H + 20), 6, fill=(255, 255, 255), outline=LINE, width=S)
    bar(d, 168, 94, 170, 12, (86, 88, 110))
    bar(d, 168, 116, 110, 6, MUTED)
    text_lines(d, 168, 138, 290, 5, 13, 5, (214, 215, 226), seed=1)
    grad = np.linspace(0, 1, 120 * S)[None, :, None]
    blk = (np.array(SOFT["peach"]) * (1 - grad) + np.array(SOFT["rose"]) * grad)
    blk = np.repeat(blk, 76 * S, axis=0).astype(np.uint8)
    img.paste(Image.fromarray(blk), (168 * S, 212 * S))
    d.ellipse([220 * S, 226 * S, 252 * S, 258 * S], fill=(255, 238, 214))
    d.polygon([(168 * S, 288 * S), (206 * S, 250 * S), (236 * S, 270 * S), (262 * S, 244 * S), (288 * S, 288 * S)], fill=(206, 150, 150))
    text_lines(d, 302, 214, 160, 6, 13, 5, (214, 215, 226), seed=2)
    finish(img, "clutter-shot-docs.png", (W, H))


def shot_dashboard():
    W, H = 512, 320
    img, d = window((W, H), 90, SOFT["teal"], bg=(244, 245, 250))
    d.rectangle([0, 30 * S, 44 * S, H * S], fill=(236, 237, 245))
    for i in range(6):
        c = SOFT["teal"] if i == 1 else (206, 208, 222)
        d.ellipse([15 * S, (48 + i * 30) * S, 29 * S, (62 + i * 30) * S], fill=c)
    f_big, f_small = font("seguisb.ttf", 17), font("segoeui.ttf", 8)
    kpis = [("1,284", "+12%", SOFT["teal"]), ("38%", "+4%", SOFT["indigo"]), ("7.2k", "-3%", SOFT["rose"])]
    for i, (v, delta, c) in enumerate(kpis):
        x = 58 + i * 148
        rr(d, (x, 44, x + 138, 104), 8, fill=(255, 255, 255))
        bar(d, x + 12, 54, 54, 5, (206, 208, 222))
        d.text(((x + 12) * S, 64 * S), v, font=f_big, fill=INK)
        d.text(((x + 12) * S, 88 * S), delta, font=f_small, fill=c)
        pts = [((x + 70 + k * 7) * S, (92 - 18 * (0.5 + 0.5 * math.sin(k * 0.9 + i * 2))) * S) for k in range(9)]
        d.line(pts, fill=c, width=2 * S, joint="curve")
    # bar chart
    rr(d, (58, 116, 330, 306), 8, fill=(255, 255, 255))
    bar(d, 72, 128, 80, 6, (190, 192, 208))
    for k in range(12):
        v = 0.35 + 0.55 * (0.5 + 0.5 * math.sin(k * 0.7 + 1.3)) * (0.8 + 0.2 * ((k * 7) % 5) / 4)
        x = 76 + k * 20
        top = 290 - v * 130
        rr(d, (x, top, x + 11, 290), 3, fill=SOFT["lavender"] if k % 3 else SOFT["indigo"])
    d.line([(70 * S, 291 * S), (318 * S, 291 * S)], fill=LINE, width=S)
    # donut
    rr(d, (342, 116, 498, 306), 8, fill=(255, 255, 255))
    bar(d, 356, 128, 60, 6, (190, 192, 208))
    box = [372 * S, 150 * S, 468 * S, 246 * S]
    start = -90
    for frac, c in ((0.42, SOFT["teal"]), (0.28, SOFT["peach"]), (0.18, SOFT["lavender"]), (0.12, SOFT["butter"])):
        d.pieslice(box, start, start + frac * 360, fill=c)
        start += frac * 360
    d.ellipse([392 * S, 170 * S, 448 * S, 226 * S], fill=(255, 255, 255))
    for i, c in enumerate((SOFT["teal"], SOFT["peach"], SOFT["lavender"])):
        d.ellipse([358 * S, (262 + i * 13) * S, 366 * S, (270 + i * 13) * S], fill=c)
        bar(d, 372, 263 + i * 13, 50 + i * 12, 5, (214, 215, 226))
    finish(img, "clutter-shot-dashboard.png", (W, H))


def landscape_array(W, H, sky_top, sky_bottom, ridges, sun=None, seed=0, water=None):
    """Layered procedural ridges with atmospheric haze; returns float RGB array."""
    r = np.random.default_rng(seed)
    y = np.linspace(0, 1, H)[:, None, None]
    img = sky_top * (1 - y) + sky_bottom * y
    img = np.repeat(img, W, axis=1).astype(np.float32)
    xx, yy = np.meshgrid(np.arange(W), np.arange(H))
    if sun:
        sx, sy, sr, sc = sun
        dist = np.hypot(xx - sx * W, yy - sy * H)
        glow = np.exp(-(dist / (sr * W * 4.0)) ** 2)[..., None] * 0.55
        img = img * (1 - glow) + np.array(sc) * glow
        disc = np.clip((sr * W - dist) / 2.0 + 0.5, 0, 1)[..., None]
        img = img * (1 - disc) + np.array((255, 244, 226)) * disc
    horizon = water * H if water else H
    for base, amp, color, rough in ridges:
        xs = np.arange(W) / W
        h = np.zeros(W)
        for o in range(6):
            f = 2 ** o * 1.6
            h += (amp / (1.8 ** o)) * np.sin(2 * math.pi * f * xs + r.uniform(0, 6.28)) * (rough if o > 2 else 1)
        top = (base - h) * H
        mask = np.clip(yy - top[None, :] + 0.5, 0, 1)
        if water:
            mask *= (yy < horizon)
        # slight vertical shading inside the ridge
        shade = np.clip((yy - top[None, :]) / (0.35 * H), 0, 1)[..., None]
        col = np.array(color) * (1 - 0.12 * shade)
        img = img * (1 - mask[..., None]) + col * mask[..., None]
        # haze band just above each ridge
        haze = np.exp(-np.clip(top[None, :] - yy, 0, None) / (0.04 * H)) * (yy < top[None, :]) * 0.18
        img = img * (1 - haze[..., None]) + 255 * haze[..., None]
    return img, xx, yy


def photo_mountains():
    W, H = 512 * S, 341 * S
    ridges = [(0.52, 0.06, (206, 186, 214), 0.5), (0.60, 0.07, (176, 158, 198), 0.6),
              (0.70, 0.06, (136, 122, 172), 0.7), (0.80, 0.05, (98, 88, 140), 0.8), (0.92, 0.04, (62, 56, 98), 0.9)]
    img, xx, yy = landscape_array(W, H, np.array((150, 156, 206)), np.array((248, 206, 180)), ridges,
                                  sun=(0.68, 0.42, 0.045, (255, 214, 170)), seed=3)
    # low mist between ridges 3 and 4
    mist = np.exp(-((yy / H - 0.77) / 0.035) ** 2) * (0.25 + 0.1 * np.sin(xx / W * 9))
    img = img * (1 - mist[..., None]) + np.array((236, 222, 236)) * mist[..., None]
    vign = 1 - 0.18 * (((xx / W - 0.5) * 1.6) ** 2 + ((yy / H - 0.5) * 1.4) ** 2)
    img = np.clip(img * vign[..., None], 0, 255).astype(np.uint8)
    out = grain(Image.fromarray(img), 3.0 * S / 2)
    finish(out.filter(ImageFilter.GaussianBlur(0.6)), "clutter-photo-mountains.png", (512, 341))


def photo_sea():
    W, H = 512 * S, 341 * S
    ridges = [(0.555, 0.012, (150, 132, 170), 0.4)]
    img, xx, yy = landscape_array(W, H, np.array((122, 146, 196)), np.array((252, 190, 160)), ridges,
                                  sun=(0.38, 0.50, 0.05, (255, 196, 150)), seed=8, water=0.56)
    r = np.random.default_rng(11)
    sea = yy >= 0.56 * H
    t = np.clip((yy - 0.56 * H) / (0.44 * H), 0, 1)
    sea_col = np.array((236, 170, 160)) * (1 - t[..., None]) + np.array((78, 96, 150)) * t[..., None]
    # sun reflection column broken by wave streaks
    streak = np.zeros((H, W))
    for _ in range(420):
        yv = int(0.56 * H + (r.random() ** 1.6) * 0.44 * H)
        xc = 0.38 * W + r.normal(0, 0.035 * W * (1 + 3 * (yv / H - 0.56)))
        ln = r.uniform(8, 40) * S * (1 + 2 * (yv / H - 0.56))
        x0, x1 = int(max(0, xc - ln)), int(min(W, xc + ln))
        streak[yv:yv + S, x0:x1] = np.maximum(streak[yv:yv + S, x0:x1], r.uniform(0.3, 0.9))
    streak = np.asarray(Image.fromarray((streak * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2 * S))) / 255.0
    waves = 0.06 * np.sin(yy / S * (0.6 + 2.5 * t) + np.sin(xx / W * 12) * 2)
    sea_col = sea_col * (1 + waves[..., None])
    sea_col = sea_col * (1 - streak[..., None] * 0.8) + np.array((255, 232, 206)) * streak[..., None] * 0.8
    img = np.where(sea[..., None], sea_col, img)
    # foreground dune
    top = (0.86 + 0.05 * np.sin(np.arange(W) / W * 3.4 + 0.6)) * H
    dune = np.clip(yy - top[None, :] + 0.5, 0, 1)
    img = img * (1 - dune[..., None]) + np.array((214, 170, 150)) * dune[..., None] * (1 - 0.15 * np.clip((yy - top[None, :]) / (0.1 * H), 0, 1))[..., None]
    img = np.clip(img, 0, 255).astype(np.uint8)
    out = grain(Image.fromarray(img), 3.0 * S / 2)
    finish(out.filter(ImageFilter.GaussianBlur(0.5)), "clutter-photo-sea.png", (512, 341))


def shot_gallery():
    """A full-screen style capture: wallpaper, one photo-browser window, generic taskbar."""
    W, H = 512, 320
    y = np.linspace(0, 1, H * S)[:, None, None]
    x = np.linspace(0, 1, W * S)[None, :, None]
    wall = np.array((196, 204, 236)) * (1 - y) + np.array((240, 208, 214)) * y
    wall = wall * (1 - 0.25 * x) + np.array((232, 224, 246)) * 0.25 * x
    img = Image.fromarray(np.clip(wall, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(img)
    # window
    win, wd = window((380, 250), 96, SOFT["peach"], bg=(250, 250, 252))
    tiles = [SOFT["peach"], SOFT["mint"], SOFT["sky"], SOFT["lavender"], SOFT["butter"], SOFT["rose"],
             SOFT["teal"], SOFT["indigo"], (228, 210, 190), (190, 214, 204), (214, 196, 226), (246, 214, 190)]
    rr(wd, (10, 40, 92, 58), 5, fill=(236, 237, 245))
    rr(wd, (98, 40, 150, 58), 5, fill=(236, 237, 245))
    for i, c in enumerate(tiles):
        cx, cy = 10 + (i % 4) * 92, 68 + (i // 4) * 60
        rr(wd, (cx, cy, cx + 84, cy + 52), 5, fill=c)
        lc = tuple(max(0, v - 50) for v in c)
        if i % 3 == 0:
            wd.polygon([(cx * S, (cy + 52) * S), ((cx + 30) * S, (cy + 22) * S), ((cx + 52) * S, (cy + 40) * S),
                        ((cx + 66) * S, (cy + 30) * S), ((cx + 84) * S, (cy + 52) * S)], fill=lc)
        elif i % 3 == 1:
            wd.ellipse([(cx + 26) * S, (cy + 10) * S, (cx + 58) * S, (cy + 42) * S], fill=lc)
        else:
            wd.rectangle([cx * S, (cy + 34) * S, (cx + 84) * S, (cy + 40) * S], fill=lc)
            wd.ellipse([(cx + 58) * S, (cy + 8) * S, (cx + 72) * S, (cy + 22) * S], fill=(255, 246, 230))
    mask = Image.new("L", win.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, win.width - 1, win.height - 1], radius=8 * S, fill=255)
    shadow = Image.new("L", (win.width + 40 * S, win.height + 40 * S), 0)
    ImageDraw.Draw(shadow).rounded_rectangle([20 * S, 26 * S, win.width + 20 * S, win.height + 26 * S], radius=10 * S, fill=70)
    shadow = shadow.filter(ImageFilter.GaussianBlur(9 * S))
    img.paste((60, 56, 90), (46 * S, 10 * S), shadow)
    img.paste(win, (66 * S, 22 * S), mask)
    # taskbar with generic centred tiles
    d.rectangle([0, (H - 24) * S, W * S, H * S], fill=(238, 236, 246))
    for i in range(6):
        cx = W / 2 - 3 * 22 + i * 22
        rr(d, (cx + 3, H - 19, cx + 17, H - 5), 4, fill=list(SOFT.values())[(i * 3) % 8] if i else (120, 124, 160))
    bar(d, W - 44, H - 16, 30, 5, (170, 172, 190))
    finish(img, "clutter-shot-gallery.png", (W, H))


def shot_chat():
    W, H = 512, 320
    img, d = window((W, H), 70, SOFT["mint"], bg=(250, 250, 252))
    d.rectangle([0, 30 * S, 150 * S, H * S], fill=(243, 244, 249))
    rr(d, (10, 40, 140, 58), 9, fill=(232, 233, 243))
    for i in range(7):
        y = 70 + i * 34
        if i == 1:
            rr(d, (6, y - 5, 144, y + 29), 7, fill=(226, 236, 232))
        d.ellipse([12 * S, y * S, 36 * S, (y + 24) * S], fill=list(SOFT.values())[(i * 5) % 8])
        bar(d, 44, y + 4, 44 + (i * 13) % 36, 6, (170, 172, 190))
        bar(d, 44, y + 15, 70 + (i * 11) % 24, 5, (214, 215, 226))
    d.line([(150 * S, 30 * S), (150 * S, H * S)], fill=LINE, width=S)
    d.ellipse([164 * S, 40 * S, 186 * S, 62 * S], fill=SOFT["peach"])
    bar(d, 194, 47, 80, 7, (150, 152, 172))
    d.line([(150 * S, 70 * S), (W * S, 70 * S)], fill=LINE, width=S)
    msgs = [(0, 150, 2), (1, 120, 1), (0, 190, 2), (1, 90, 1), (0, 130, 1)]
    y = 82
    for side, w, rows in msgs:
        h = 12 + rows * 11
        x0 = 166 if side == 0 else W - 16 - w
        rr(d, (x0, y, x0 + w, y + h), 9, fill=(236, 237, 245) if side == 0 else (198, 226, 214))
        for k in range(rows):
            bar(d, x0 + 10, y + 8 + k * 11, (w - 20) * (0.6 if k == rows - 1 and rows > 1 else 0.9), 5,
                (190, 192, 208) if side == 0 else (132, 180, 160))
        y += h + 8
    rr(d, (164, H - 36, W - 14, H - 10), 13, fill=(255, 255, 255), outline=LINE, width=S)
    bar(d, 180, H - 26, 120, 6, (214, 215, 226))
    d.ellipse([(W - 38) * S, (H - 32) * S, (W - 18) * S, (H - 14) * S], fill=SOFT["teal"])
    finish(img, "clutter-shot-chat.png", (W, H))


def receipt():
    W, H = 250, 512
    img = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
    paper = Image.new("RGBA", img.size, (250, 248, 242, 255))
    # torn zigzag top and bottom edges as alpha
    mask = Image.new("L", img.size, 0)
    md = ImageDraw.Draw(mask)
    tooth = 10
    pts = [(0, tooth * S)]
    for i in range(W // tooth + 1):
        pts += [((i * tooth + tooth / 2) * S, 0), ((i * tooth + tooth) * S, tooth * S)]
    pts += [(W * S, (H - tooth) * S)]
    for i in range(W // tooth, -1, -1):
        pts += [((i * tooth + tooth / 2) * S, H * S), (i * tooth * S, (H - tooth) * S)]
    md.polygon(pts, fill=255)
    # faint thermal fade / fold shading
    a = np.asarray(paper).astype(np.float32)
    yy = np.linspace(0, 1, H * S)[:, None]
    fold = 1 - 0.035 * np.exp(-((yy - 0.47) / 0.02) ** 2) - 0.02 * yy
    a[..., :3] *= fold[..., None]
    paper = grain(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA"), 2.0)
    img.paste(paper, (0, 0), mask)
    d = ImageDraw.Draw(img)
    mono, monob = font("consola.ttf", 11), font("consolab.ttf", 15)
    ink = (70, 70, 82, 255)

    def center(y, s, f=mono):
        w = d.textlength(s, font=f)
        d.text(((W * S - w) / 2, y * S), s, font=f, fill=ink)

    def row(y, left, right, f=mono):
        d.text((22 * S, y * S), left, font=f, fill=ink)
        w = d.textlength(right, font=f)
        d.text(((W - 22) * S - w, y * S), right, font=f, fill=ink)

    def dashed(y):
        for x in range(22, W - 22, 8):
            d.line([(x * S, y * S), ((x + 4) * S, y * S)], fill=(150, 150, 160, 255), width=S)

    center(34, "RECEIPT", monob)
    center(56, "No. 0926   26/09  10:42")
    dashed(80)
    items = [("Flat white", "4.20"), ("Oat cookie", "2.40"), ("Croissant", "3.10"),
             ("Sparkling water", "2.80"), ("Notebook A5", "6.90"), ("Pens x3", "4.50")]
    for i, (l, r) in enumerate(items):
        row(94 + i * 20, l, r)
    dashed(222)
    row(236, "Subtotal", "23.90")
    row(256, "Tax", "1.91")
    row(282, "TOTAL", "25.81", monob)
    dashed(310)
    row(324, "Card", "**** 4417")
    row(344, "Auth", "081922")
    center(384, "Thank you!")
    # barcode-ish stripes
    r = np.random.default_rng(4)
    x = 40
    while x < W - 40:
        w = int(r.integers(1, 4))
        d.rectangle([x * S, 414 * S, (x + w) * S, 450 * S], fill=ink)
        x += w + int(r.integers(1, 3))
    center(456, "0926 0010 4217 7731")
    finish(img, "clutter-receipt.png", (W, H))


def memo():
    W, H = 440, 512
    img = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
    yy, xx = np.mgrid[0:H * S, 0:W * S].astype(np.float32)
    base = np.array((252, 234, 150), np.float32)
    shade = 1 - 0.06 * (yy / (H * S)) - 0.03 * (xx / (W * S))
    top_band = (yy < 60 * S) * 0.04
    rgb = base * (shade - top_band)[..., None]
    alpha = np.full(yy.shape, 255, np.float32)
    # lifted bottom-right corner: cut a curved triangle and draw the curl
    c = 70 * S
    cut = (xx + yy) > (W * S + H * S - c)
    alpha[cut] = 0
    note = Image.fromarray(np.dstack([np.clip(rgb, 0, 255), alpha]).astype(np.uint8), "RGBA")
    note = grain(note, 2.0)
    img.alpha_composite(note)
    d = ImageDraw.Draw(img)
    d.polygon([((W * S - c), H * S), (W * S, (H * S - c)), ((W * S - c * 0.78), (H * S - c * 0.78))], fill=(232, 208, 118, 255))
    d.line([((W * S - c), H * S), (W * S, (H * S - c))], fill=(214, 188, 100, 255), width=S)
    hand, handb = font("Inkfree.ttf", 26), font("Inkfree.ttf", 34)
    ink = (52, 64, 110, 255)
    d.text((34 * S, 34 * S), "To do  (Fri)", font=handb, fill=ink)
    d.line([(34 * S, 84 * S), (230 * S, 80 * S)], fill=ink, width=2 * S)
    lines = ["send brief to Mia", "invoice 0926 !!", "pick 2 fonts", "back up photos", "call printer re: proofs", "tidy desktop..."]
    for i, s in enumerate(lines):
        y = 108 + i * 56
        d.rectangle([36 * S, (y + 10) * S, 54 * S, (y + 28) * S], outline=ink, width=2 * S)
        if i in (0, 2):
            d.line([(38 * S, (y + 18) * S), (45 * S, (y + 26) * S), (60 * S, (y + 4) * S)], fill=(190, 70, 70, 255), width=3 * S)
        d.text((68 * S, y * S), s, font=hand, fill=ink)
    d.line([(68 * S, 222 * S), (220 * S, 220 * S)], fill=ink, width=2 * S)  # strike "pick 2 fonts"
    finish(img, "clutter-memo.png", (W, H))


def main():
    shot_docs()
    shot_dashboard()
    shot_gallery()
    shot_chat()
    photo_mountains()
    photo_sea()
    receipt()
    memo()


if __name__ == "__main__":
    main()
