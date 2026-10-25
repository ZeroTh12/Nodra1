"""Prepare isolated native fixtures for the 2026-09 trailer (v3).

uv run --with pillow --with numpy python extras/pecofence-promo/scripts/prepare-trailer-fixtures.py

Reuses the original graphic studies and paper wallpapers made by
scripts/prepare-store-v2.py (.cache/store-v2). Geometry is in physical pixels of
a 2560 x 1440 plate centred on the 3840 x 2160 capture display; the capture
runner converts it to DIPs.
"""
import copy
import json
import shutil
import sys
import uuid
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
store = __import__("prepare-store-v2")  # fence(), font(), wallpaper(), studies()

PROMO = ROOT / "extras/pecofence-promo"
BASE = PROMO / ".capture/reviewed/trailer-v3"
ASSETS = ROOT / ".cache/store-v2"
STUDIES = ASSETS / "studies"
EXTRA = ROOT / ".cache/promo2/files"

SCENES = ("overview", "dark", "auto", "tabs", "ai", "styles")
INCOMING = ["Form study.png", "Launch checklist.md", "Sol study.png", "Q3 report.pdf"]


# Physical screen px: the plate sits at (640, 360) on the 3840 x 2160 capture display.
DOCS_RECT = f"{640 + 1120},{360 + 840},800,345"
CLI_STEPS = {
    "ai": [
        {"t": 4.0, "n": "create", "a": ["fence", "create", "--title", "Docs", "--rect", DOCS_RECT]},
        {"t": 5.2, "n": "auto-height", "a": ["fence", "set", "Docs", "autoHeight", "true"]},
        {"t": 6.4, "n": "rule-add", "a": ["rule", "add", "--name", "PDFs", "--ext", "pdf", "--to", "Docs", "--index", "0"]},
        {"t": 7.4, "n": "rule-apply", "a": ["rule", "apply"]},
        {"t": 10.0, "n": "icons", "a": ["fence", "set", "--all", "iconSize", "96"]},
        {"t": 12.5, "n": "tint", "a": ["fence", "set", "--all", "tint", "#E86A5C"]},
    ],
    "styles": [
        {"t": 3.5, "n": "s1-dark", "a": ["settings", "set", "theme", "dark"]},
        {"t": 5.5, "n": "s2-glass", "a": ["settings", "set", "themeStyle", "liquidGlass"]},
        {"t": 7.5, "n": "s3-clear", "a": ["fence", "set", "--all", "opacity", "clear"]},
        {"t": 9.5, "n": "s4-tint", "a": ["fence", "set", "--all", "tint", "#E86A5C"]},
        {"t": 11.5, "n": "s5-fluent", "a": ["settings", "set", "themeStyle", "fluent"]},
        {"t": 13.5, "n": "s6-light", "a": ["settings", "set", "theme", "light"]},
        {"t": 15.5, "n": "s7-icons", "a": ["fence", "set", "--all", "iconSize", "96"]},
    ],
}

def document(name, kicker, title, lines, accent):
    page = Image.new("RGB", (850, 1100), "#fbfaf7")
    d = ImageDraw.Draw(page)
    d.text((70, 60), kicker, font=store.font(22), fill=accent)
    d.text((70, 150), title, font=store.font(60, True), fill="#272638", spacing=8)
    d.line((70, 360, 780, 360), fill="#d9d2c8", width=2)
    for i, line in enumerate(lines):
        d.text((70, 420 + i * 70), line, font=store.font(26), fill="#3c3b48")
    page.save(EXTRA / name, resolution=144)


def extra_files():
    EXTRA.mkdir(parents=True, exist_ok=True)
    document("Invoice 0926.pdf", "TERRA STUDIO / INVOICE", "Invoice\nNo. 0926", ["Identity system", "Website design", "Launch images"], "#8d5445")
    document("Contract.pdf", "TERRA STUDIO / AGREEMENT", "Service\nagreement", ["Scope of work", "Timeline", "Terms"], "#335c80")
    document("Q3 report.pdf", "TERRA STUDIO / REVIEW", "Quarterly\nreport", ["Highlights", "Projects", "Next quarter"], "#175e5b")


def settings_for(fixture, dark):
    reference = json.loads((PROMO / ".capture/reviewed/auto-v2/app/config/config.json").read_text(encoding="utf-8-sig"))
    settings = copy.deepcopy(reference["settings"])
    settings.update(language="en", theme="dark" if dark else "light", themeStyle="liquidGlass",
                    hideRealIcons=False, showRealIconsWhenFencesHidden=False, desktopPath=str(fixture), autostart=False)
    settings["peek"] = {"enabled": False, "dim": True, "hotkey": "ctrlAltSpace"}
    settings["snapping"]["sizeToCells"] = False
    return settings, reference["layouts"][0]["fingerprint"]


def portal_folders(case):
    for group in ("Projects", "Inspiration", "Today"):
        (case / group).mkdir(exist_ok=True)
    for title in ("Brand", "Website", "Campaign", "Archive"):
        (case / "Projects" / title).mkdir(exist_ok=True)
    for title in ("Creative brief.pdf", "Launch checklist.md"):
        shutil.copy2(STUDIES / title, case / "Projects" / title)
    for p in STUDIES.glob("*.png"):
        shutil.copy2(p, case / "Inspiration" / p.name)
    for title in ("Creative brief.pdf", "Meeting notes.txt", "Launch checklist.md"):
        shutil.copy2(STUDIES / title, case / "Today" / title)


def prepare(name):
    case = BASE / name
    app = case / "app"
    fixture = case / "desktop-fixture"
    (app / "config").mkdir(parents=True, exist_ok=True)
    if fixture.exists():
        shutil.rmtree(fixture)
    fixture.mkdir()
    portal_folders(case)
    settings, fingerprint = settings_for(fixture, name == "dark")
    config = {"schemaVersion": 1, "settings": settings, "items": {}, "snapshots": [], "undoLog": [],
              "rules": {"defaultTarget": "inbox", "keepUpdated": False, "list": []},
              "layouts": [{"fingerprint": fingerprint, "fences": []}]}
    fence = store.fence
    inbox = fence("Capture inbox", (-600, -200, 300, 100), kind="inbox", icon=32)
    inbox["rolledUp"] = True
    commands = ["sleep 1000", "pin-test-windows", "sleep 400"]
    if name in ("overview", "dark"):
        fences = [fence("Projects", (90, 332, 680, 590), case / "Projects", icon=64),
                  fence("Inspiration", (840, 392, 880, 715), case / "Inspiration", icon=96),
                  fence("Today", (1790, 547, 675, 355), case / "Today", icon=64)]
        commands += ["sleep 9000"]
    elif name == "auto":
        for title in ("Terra study.png", "Still study.png", "Creative brief.pdf", "Meeting notes.txt"):
            shutil.copy2(STUDIES / title, fixture / title)
        fences = [fence("Images", (200, 420, 1260, 640), kind="virtual", icon=96),
                  fence("Documents", (1560, 440, 800, 600), kind="virtual", icon=64)]
        for f, extensions in zip(fences, [["png"], ["pdf", "txt", "md"]]):
            config["rules"]["list"].append({"id": str(uuid.uuid4()), "name": f["title"], "enabled": True,
                "target": {"fence": f["id"]}, "allOf": [{"cond": "ext", "value": extensions}], "priorityClass": "type"})
        config["rules"]["keepUpdated"] = True
        commands += ["sleep 12000"]
    elif name == "tabs":
        fences = [fence("Projects", (190, 330, 1060, 800), case / "Projects", icon=96),
                  fence("Inspiration", (1310, 330, 1060, 800), case / "Inspiration", icon=96)]
        commands += ["sleep 3000", "merge Inspiration Projects", "sleep 3000", "activate Projects",
                     "sleep 2500", "activate Inspiration", "sleep 2500", "activate Projects", "sleep 2500"]
    elif name in ("ai", "styles"):
        for title in ("Creative brief.pdf", "Meeting notes.txt", "Launch checklist.md", "Assets.zip",
                      "Project links.url", "Terra study.png", "Still study.png"):
            shutil.copy2(STUDIES / title, fixture / title)
        for title in ("Invoice 0926.pdf", "Contract.pdf", "Q3 report.pdf"):
            shutil.copy2(EXTRA / title, fixture / title)
        settings["iconSize"] = 64
        desk = fence("Desktop", (1120, 110, 800, 700), kind="inbox", icon=64)
        gallery = fence("Inspiration", (1950, 110, 600, 700), case / "Inspiration", icon=64)
        for f in (desk, gallery):
            f["view"]["autoHeight"] = True
        fences = [desk, gallery]
        inbox = None
        commands += ["sleep 18000"]
        steps = CLI_STEPS[name]
        if name == "styles":
            settings["themeStyle"] = "fluent"
        (case / "cli-steps.json").write_text(json.dumps(steps, indent=1), encoding="utf-8")
    fences = fences + ([inbox] if inbox else [])
    config["layouts"][0]["fences"] = fences
    (case / "template.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    (case / "config.final.json").write_text(json.dumps(finalize(config), indent=2), encoding="utf-8")
    commands += ["dump capture-end", "exit"]
    (case / "commands.txt").write_text("\n".join(commands), encoding="utf-8")


def monitor():
    """Primary monitor device, bounds, work area (physical px) and DPI."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))

    class MONITORINFOEXW(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                    ("dwFlags", wintypes.DWORD), ("szDevice", wintypes.WCHAR * 32)]
    user32.MonitorFromPoint.restype = ctypes.c_void_p
    hmon = user32.MonitorFromPoint(wintypes.POINT(0, 0), 1)
    info = MONITORINFOEXW()
    info.cbSize = ctypes.sizeof(info)
    user32.GetMonitorInfoW(ctypes.c_void_p(hmon), ctypes.byref(info))
    dpi = user32.GetDpiForSystem()
    m, w = info.rcMonitor, info.rcWork
    return info.szDevice, (m.right - m.left, m.bottom - m.top), (w.right - w.left, w.bottom - w.top), dpi


MON = None


def finalize(template):
    """Resolve plate-relative physical geometry to the capture monitor's DIPs."""
    global MON
    MON = MON or monitor()
    device, (sw, sh), (ww, wh), dpi = MON
    assert (sw, sh) == (3840, 2160), f"trailer capture expects 3840x2160, found {sw}x{sh}"
    scale = dpi / 96
    px, py = (sw - 2560) // 2, (sh - 1440) // 2
    config = copy.deepcopy(template)
    config["layouts"][0]["fingerprint"] = [{"devicePath": device, "workDip": [ww / scale, wh / scale], "dpi": dpi}]
    for f in config["layouts"][0]["fences"]:
        g = f["geometry"]
        g.update(monitor=device, x=(px + g["x"]) / scale, y=(py + g["y"]) / scale, w=g["w"] / scale, h=g["h"] / scale,
                 workW=ww / scale, workH=wh / scale)
        f["expandedH"] = g["h"]
    return config


def main():
    if not (STUDIES / "Terra study.png").exists():
        store.studies()
    extra_files()
    BASE.mkdir(parents=True, exist_ok=True)
    for name in SCENES:
        prepare(name)
    for name in INCOMING:
        src = STUDIES / name if (STUDIES / name).exists() else EXTRA / name
        shutil.copy2(src, BASE / "auto" / f"incoming-{name}")
    print(f"Prepared {len(SCENES)} isolated fixtures in {BASE}")


if __name__ == "__main__":
    main()
