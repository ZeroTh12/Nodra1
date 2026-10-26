# Rebuild crates/app/assets/pecofence.ico from .cache/nodra-render-1024.png with a
# 22%-of-side rounded-corner mask (4x supersampled, antialiased), matching the tray,
# the settings caption and the fences' radius language. The tray's nodra-64.bgra stays
# full-bleed: visuals.rs applies the same mask at its output, so the source must not be
# pre-rounded.
# Usage: python scripts/round-brand-ico.py
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SRC = ROOT / ".cache" / "nodra-render-628.png"
ICO_OUT = ROOT / "crates" / "app" / "assets" / "pecofence.ico"
ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
CORNER_RADIUS = 0.22  # of the side, same as the tray/caption mask

src = Image.open(SRC).convert("RGBA")
if src.size[0] != src.size[1]:
    raise SystemExit(f"source is not square: {src.size}")
size = src.size[0]

# Rounded mask at 4x, downsampled with LANCZOS for a clean antialiased edge.
scale = 4
big = Image.new("L", (size * scale, size * scale), 0)
ImageDraw.Draw(big).rounded_rectangle(
    (0, 0, size * scale - 1, size * scale - 1),
    radius=round(size * CORNER_RADIUS * scale),
    fill=255,
)
mask = big.resize((size, size), Image.LANCZOS)
out = src.copy()
out.putalpha(ImageChops.multiply(out.getchannel("A"), mask))
out.save(ROOT / ".cache" / "nodra-rounded-1024.png")

# One rounded base; Pillow derives every frame by downscaling it, which keeps the
# antialiased corners at every size.
out.save(ICO_OUT, format="ICO", sizes=[(s, s) for s in ICO_SIZES])
print(f"ico written: {ICO_OUT} ({ICO_OUT.stat().st_size} bytes, base {size}px, radius {CORNER_RADIUS:.0%})")
