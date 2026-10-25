"""Write public/trailer-v3/assets-manifest.json for the trailer (v3) visual assets.

uv run --with pillow python extras/pecofence-promo/scripts/write-trailer-assets-manifest.py

Run after extract-trailer-icons.ps1, make-trailer-clutter.py and measure-trailer-targets.py.
Lists every produced file with byte size, pixel size, how it was made and notes (brand flags for
shell icons that show a third-party / application logo).
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
PROMO = ROOT / "extras/pecofence-promo"
PUB = PROMO / "public/trailer-v3"
CACHE = ROOT / ".cache/promo2"
SCRIPTS = "extras/pecofence-promo/scripts"

ICON_METHOD = (f"{SCRIPTS}/extract-trailer-icons.ps1: IShellItemImageFactory::GetImage(256x256, SIIGBF_ICONONLY) on an empty "
               "dummy file in .cache/promo2/iconsrc; GetDIBits top-down 32 bpp; the shell bitmap is straight alpha here "
               "(colour above alpha in semi-transparent pixels), saved unchanged as RGBA PNG")
# brand: the icon shows a third-party or application logo the editor may want to avoid.
ICONS = {
    "folder.png": (False, "Windows 11 folder icon (shell32)."),
    "pdf.png": (False, "PDF file icon of the current handler, Microsoft Edge (MSEdgePDF): generic page with a red 'PDF' band, no logo. "
                       "Same icon the fences show."),
    "txt.png": (False, "Windows Notepad text-document icon (lined page), no logo."),
    "md.png": (True, "Visual Studio Code markdown icon: page with a blue arrow and the VS Code logo badge (handler VSCode.md). "
                     "Same icon the fences show for Launch checklist.md."),
    "zip.png": (True, "7-Zip archive icon ('7z' logo). 7-Zip has no large icon, so the shell centres its 48 px glyph in a faint 256 px tile. "
                      "The fences instead draw the 48 px glyph at 2x inside the tile: use zip-48.png (nearest-neighbour x2) to match the footage."),
    "zip-48.png": (True, "Native 48 px 7-Zip glyph (IShellItemImageFactory at 48x48); the fences draw this at 2x (96 px) inside a 128/192 px tile."),
    "url.png": (True, "Internet shortcut icon for 'Project links.url' (URL=https://example.com/): page with the Google Chrome logo "
                      "(default browser). Same icon the fences show."),
    "mp4.png": (True, "MP4 icon of the current handler PotPlayer (purple play triangle + 'MP4' text)."),
    "docx.png": (True, "Microsoft Word document icon (Word logo)."),
    "xlsx.png": (True, "Microsoft Excel workbook icon (Excel logo)."),
    "png-generic.png": (False, "PNG file-type icon of the Windows Photos app (page with the Photos picture glyph); inbox Windows app, "
                               "no third-party brand."),
    "exe.png": (False, "Generic application icon: the shell's fallback for an empty dummy 'setup.exe' (nothing was executed)."),
}


def entry(path, method, notes="", **extra):
    e = {"file": str(path.relative_to(PUB)).replace("\\", "/"), "bytes": path.stat().st_size,
         "sha256": hashlib.sha256(path.read_bytes()).hexdigest()[:16]}
    if path.suffix == ".png":
        with Image.open(path) as im:
            e["size"] = [im.width, im.height]
            e["mode"] = im.mode
    e["method"] = method
    if notes:
        e["notes"] = notes
    e.update(extra)
    return e


def main():
    meta = json.loads((PUB / "icons/icons-meta.json").read_text(encoding="utf-8-sig"))
    files = []
    for name, (brand, note) in ICONS.items():
        key = name[:-4]
        info = meta["icons"].get(key.replace("-48", ""), {})
        files.append(entry(PUB / "icons" / name, ICON_METHOD if key != "zip-48" else ICON_METHOD.replace("256x256", "48x48"),
                           note, brand=brand, handler={k: info.get(k) for k in ("friendlyApp", "progId", "defaultIcon")},
                           alpha="straight (non-premultiplied)"))
    for src, t in meta["thumbs"].items():
        files.append(entry(PUB / "icons" / t["file"],
                           f"{SCRIPTS}/extract-trailer-icons.ps1: IShellItemImageFactory::GetImage(256x256, SIIGBF_THUMBNAILONLY) on "
                           f".cache/store-v2/studies/{src}",
                           f"The shell's own thumbnail of {src} (original procedural study, 900x1120), aspect-fit 206x256, opaque. "
                           "Orientation verified against the source (mean abs error ~1.5 upright vs 12-32 flipped).", brand=False, source=src))
    files.append(entry(PUB / "icons/icons-meta.json", f"{SCRIPTS}/extract-trailer-icons.ps1",
                       "Raw export log: bitmap stats (alpha form), handler friendly name / ProgID / default-icon path per type."))
    clutter = {
        "clutter-shot-docs.png": "Abstract document-editor window: toolbar chips, sidebar list, page with heading/paragraph bars and an illustration block.",
        "clutter-shot-dashboard.png": "Abstract analytics window: three KPI cards (numbers only), bar chart, donut chart.",
        "clutter-shot-gallery.png": "Full-screen style capture: pastel wallpaper, photo-browser window with a 4x3 tile grid, generic taskbar.",
        "clutter-shot-chat.png": "Abstract messaging window: conversation list with avatar dots, chat bubbles, input field.",
        "clutter-photo-mountains.png": "Procedural dusk mountain range: layered sine-octave ridges, sun glow, mist band, vignette, grain.",
        "clutter-photo-sea.png": "Procedural sunset seascape: sky gradient, sun on the horizon, broken reflection streaks, dune foreground, grain.",
        "clutter-receipt.png": "Thermal-paper receipt (Consolas): generic items and totals, no shop name; zig-zag torn edges in alpha.",
        "clutter-memo.png": "Yellow sticky note with a handwritten (Ink Free) to-do list; lifted corner in alpha.",
    }
    for name, note in clutter.items():
        files.append(entry(PUB / "clutter" / name, f"{SCRIPTS}/make-trailer-clutter.py (Pillow + numpy, drawn at 2x, Lanczos down to 512 px long side)",
                           note + " Original artwork: no stock, screenshots, logos or brand names.", brand=False))
    files.append(entry(PUB / "targets.json", f"{SCRIPTS}/measure-trailer-targets.py (numpy + OpenCV)",
                       "Fence rects, item icon/label boxes (overview/dark t=4, auto arrivals + t=4/12, ai t=4/7/9.5/12.5/15, tabs t=4/8), "
                       "tab-strip boxes, measured change times. Physical px of the 3840x2160 frame. Visual checks: "
                       ".cache/promo2/targets-check-<take>.png."))
    stills = {"overview-4s.png": ("overview.mp4", 4.0), "dark-4s.png": ("dark.mp4", 4.0), "ai-3s.png": ("ai.mp4", 3.0),
              "ai-15s.png": ("ai.mp4", 15.0), "auto-12s.png": ("auto.mp4", 12.0), "tabs-8s.png": ("tabs.mp4", 8.0)}
    for name, (video, t) in stills.items():
        files.append(entry(PUB / "stills" / name,
                           f"{SCRIPTS}/measure-trailer-targets.py: ffmpeg -ss {t} -i {video} -frames:v 1, BT.709 limited -> full range RGB24",
                           "Full-resolution frame (first frame with pts >= t); identical to the frame the targets were measured on.",
                           video=f"trailer-v3/{video}", t=t))
    out = {"generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "root": "extras/pecofence-promo/public/trailer-v3",
           "scripts": [f"{SCRIPTS}/extract-trailer-icons.ps1", f"{SCRIPTS}/make-trailer-clutter.py",
                       f"{SCRIPTS}/measure-trailer-targets.py", f"{SCRIPTS}/write-trailer-assets-manifest.py"],
           "rebuild": ["powershell.exe -NoProfile -ExecutionPolicy Bypass -File extras\\pecofence-promo\\scripts\\extract-trailer-icons.ps1",
                       "uv run --with pillow --with numpy python extras/pecofence-promo/scripts/make-trailer-clutter.py",
                       "uv run --with numpy --with pillow --with opencv-python-headless python extras/pecofence-promo/scripts/measure-trailer-targets.py",
                       "uv run --with pillow python extras/pecofence-promo/scripts/write-trailer-assets-manifest.py"],
           "brandIcons": [f["file"] for f in files if f.get("brand")],
           "files": files,
           "validation": sorted(str(p.relative_to(ROOT)).replace("\\", "/") for p in CACHE.glob("targets-check-*.png"))}
    (PUB / "assets-manifest.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(len(files), "files;", "brand:", out["brandIcons"])


if __name__ == "__main__":
    main()
