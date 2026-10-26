"""Regenerate ALL icons from Nodra.svg (the user-specified brand icon).

Outputs:
  crates/app/assets/pecofence.ico     — 9-frame ICO (16..256 px) for EXE embed
  crates/app/assets/nodra-64.bgra     — 64x64 BGRA raw bytes for tray / caption
  .cache/nodra-brand-256.png          — 256x256 PNG for settings.html brand-mark base64
  .cache/nodra-brand-base64.txt        — the base64 data URI

Usage: python scripts/regen-all-icons.py
"""
import base64
import sys
from pathlib import Path

import cairosvg
from PIL import Image, ImageChops, ImageDraw

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SVG = ROOT / "Nodra.svg"
ICO_OUT = ROOT / "crates" / "app" / "assets" / "pecofence.ico"
BGRA_OUT = ROOT / "crates" / "app" / "assets" / "nodra-64.bgra"
CACHE = ROOT / ".cache"
CACHE.mkdir(exist_ok=True)

ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)

# The brand square must not read as a hard-edged tile in the taskbar, the Start menu or the
# installer: a rounded-corner alpha mask, at the squircle proportion Windows app icons use.
CORNER_RADIUS = 0.18


def round_corners(img: Image.Image) -> Image.Image:
    """Clip `img` to a rounded square, with the mask drawn at 4x and downsampled (no jaggies)."""
    size = img.size[0]
    scale = 4
    big = Image.new("L", (size * scale, size * scale), 0)
    ImageDraw.Draw(big).rounded_rectangle(
        (0, 0, size * scale - 1, size * scale - 1),
        radius=max(1, round(size * CORNER_RADIUS * scale)),
        fill=255,
    )
    mask = big.resize((size, size), Image.LANCZOS)
    out = img.convert("RGBA")
    out.putalpha(ImageChops.multiply(out.getchannel("A"), mask))
    return out


def render(size: int) -> Image.Image:
    """Render Nodra.svg at `size` x `size`, rounded, and return a PIL Image (RGBA)."""
    import io
    png_bytes = cairosvg.svg2png(
        url=str(SVG), output_width=size, output_height=size
    )
    img = Image.open(io.BytesIO(png_bytes))
    return round_corners(img.convert("RGBA"))


def build_ico() -> Path:
    frames = [render(s) for s in ICO_SIZES]
    ICO_OUT.parent.mkdir(parents=True, exist_ok=True)
    largest = frames[-1]  # 256
    # Pillow's ICO writer supports only "append_images" (not per-frame sizes).
    # Save the base image first with sizes= kwarg — but Pillow 10+ changed the API.
    # Use the documented approach: save largest, append smaller ones.
    largest.save(
        ICO_OUT,
        format="ICO",
        sizes=[(s, s) for s in ICO_SIZES],
        append_images=frames[:-1],
    )
    size = ICO_OUT.stat().st_size
    print(f"  wrote {ICO_OUT} ({size} bytes, sizes {ICO_SIZES})")
    return ICO_OUT


def build_bgra() -> Path:
    img = render(64)
    # BGRA byte order (Pillow is RGBA, so swap R and B)
    r, g, b, a = img.split()
    img_bgra = Image.merge("RGBA", (b, g, r, a))
    data = img_bgra.tobytes()
    BGRA_OUT.write_bytes(data)
    print(f"  wrote {BGRA_OUT} ({len(data)} bytes = 64x64x4)")
    return BGRA_OUT


def build_brand_png() -> Path:
    """Render a 256x256 PNG used as settings.html's brand-mark."""
    out = CACHE / "nodra-brand-256.png"
    img = render(256)
    img.save(out, format="PNG")
    # Also write the base64 data URI so we can paste into settings.html
    b64 = base64.b64encode(out.read_bytes()).decode("ascii")
    b64_path = CACHE / "nodra-brand-base64.txt"
    b64_path.write_text(b64, encoding="ascii")
    print(f"  wrote {out} ({out.stat().st_size} bytes)")
    print(f"  wrote {b64_path} ({len(b64)} chars of base64)")
    return out


def main() -> int:
    if not SVG.exists():
        print(f"ERROR: {SVG} not found", file=sys.stderr)
        return 1
    print(f"Source SVG: {SVG}")
    print()
    print("1) Building pecofence.ico ...")
    build_ico()
    print()
    print("2) Building nodra-64.bgra ...")
    build_bgra()
    print()
    print("3) Building settings brand-mark PNG + base64 ...")
    build_brand_png()
    print()
    print("All icons regenerated from Nodra.svg.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
