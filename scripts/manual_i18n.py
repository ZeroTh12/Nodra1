"""Translate the animated user manual (site/manual) into the site's languages.

The zh-CN page (site/manual/page.html) and its demo scripts are the master copy. A
translation file site/manual/i18n/<lang>.json has two maps keyed by the zh-CN source:

  "page":  inner HTML of each text block of page.html (and translatable attributes)
  "stage": the body of each JavaScript string literal with Chinese in it (demo text:
           fence and file names, menu items, gesture captions, settings labels ...)

At build time the blocks and literals are replaced, so every language gets the same
page, scripts and timings. Stage strings that are the app's own UI text are prefilled
from locales/<lang>.json, so the demos show the words the app really uses.

  uv run python scripts/manual_i18n.py --source        # list the zh-CN strings
  uv run python scripts/manual_i18n.py --prefill <lang> # add missing keys (+ app UI text)
  uv run python scripts/manual_i18n.py --check          # coverage per language
"""
import argparse
import hashlib
import html
import json
import re
import shutil
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANUAL = ROOT / "site" / "manual"
CJK = re.compile(r"[　-ヿ㐀-鿿＀-￯]")

# Elements whose inner HTML is one translatable block; inline elements are kept inside it.
SEGMENT = {"title", "h1", "h2", "h3", "p", "li", "td", "th", "dt", "dd", "summary", "button",
           "figcaption", "label", "caption"}
INLINE = {"a", "b", "strong", "em", "i", "kbd", "code", "span", "q", "small", "br", "wbr", "sup",
          "sub", "svg", "path", "rect", "use", "circle", "g", "img", "mark"}
VOID = {"br", "wbr", "img", "meta", "link", "input", "source", "hr", "area", "base", "col"}
ATTRS = {"aria-label", "title", "alt", "placeholder", "data-play", "data-pause", "data-title", "content"}


class _Segments(HTMLParser):
    """Finds translatable blocks: the nearest SEGMENT ancestor of each Chinese text run, or
    else the outermost inline ancestor below the enclosing block."""

    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.source = source
        self.lines = [0]
        for m in re.finditer(r"\n", source):
            self.lines.append(m.end())
        self.stack = []      # [tag, inner_start, is_root]
        self.blocks = []     # (inner_start, inner_end)
        self.attrs = []      # (tag_start, tag_end, name, value)
        self.skip = 0

    def _offset(self):
        line, col = self.getpos()
        return self.lines[line - 1] + col

    def handle_starttag(self, tag, attrs):
        start = self._offset()
        text = self.get_starttag_text()
        for name, value in attrs:
            if name in ATTRS and value and CJK.search(value):
                self.attrs.append((start, start + len(text), name, value))
        if tag in ("script", "style"):
            self.skip += 1
        if tag not in VOID:
            self.stack.append([tag, start + len(text), False])

    def handle_startendtag(self, tag, attrs):
        start = self._offset()
        text = self.get_starttag_text()
        for name, value in attrs:
            if name in ATTRS and value and CJK.search(value):
                self.attrs.append((start, start + len(text), name, value))

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        end = self._offset()
        while self.stack:
            item = self.stack.pop()
            if item[0] in ("script", "style"):
                self.skip -= 1
            if item[2]:
                self.blocks.append((item[1], end))
            if item[0] == tag:
                break

    def handle_data(self, data):
        if self.skip or not CJK.search(data) or not self.stack:
            return
        root = None
        for i in range(len(self.stack) - 1, -1, -1):
            tag = self.stack[i][0]
            if tag in SEGMENT:
                root = i
                break
            if tag not in INLINE:
                root = i + 1 if i + 1 < len(self.stack) else i
                break
        if root is None:
            return
        # an outer block already covers this text
        if any(self.stack[j][2] for j in range(root)):
            return
        self.stack[root][2] = True


def page_segments(source):
    """[(start, end, inner_html)] blocks and [(tag_start, tag_end, attr, value)] attributes."""
    parser = _Segments(source)
    parser.feed(source)
    parser.close()
    blocks = sorted(set(parser.blocks))
    # keep only outermost blocks
    outer = []
    for s, e in blocks:
        if not any(s2 <= s and e <= e2 and (s2, e2) != (s, e) for s2, e2 in blocks):
            outer.append((s, e, source[s:e]))
    return outer, parser.attrs


def js_literals(source):
    """[(start, end, body)] of string literals (quotes excluded) that contain Chinese. Skips
    comments and regex literals; follows ${...} inside template strings."""
    out = []
    i, n = 0, len(source)
    regex_ok = True   # whether a '/' here would start a regex literal

    def scan_code(i, stop_brace):
        nonlocal regex_ok
        depth = 0
        while i < n:
            c = source[i]
            if c == "/" and source.startswith("//", i):
                i = source.find("\n", i)
                i = n if i < 0 else i
                continue
            if c == "/" and source.startswith("/*", i):
                j = source.find("*/", i + 2)
                i = n if j < 0 else j + 2
                continue
            if c in "'\"":
                j = i + 1
                while j < n and source[j] != c:
                    j += 2 if source[j] == "\\" else 1
                body = source[i + 1:j]
                if CJK.search(body):
                    out.append((i + 1, j, body))
                i = j + 1
                regex_ok = False
                continue
            if c == "`":
                i = scan_template(i + 1)
                regex_ok = False
                continue
            if c == "/" and regex_ok:
                j = i + 1
                in_class = False
                while j < n and source[j] != "\n":
                    if source[j] == "\\":
                        j += 2
                        continue
                    if source[j] == "[":
                        in_class = True
                    elif source[j] == "]":
                        in_class = False
                    elif source[j] == "/" and not in_class:
                        break
                    j += 1
                i = j + 1
                while i < n and source[i].isalpha():
                    i += 1
                regex_ok = False
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                if stop_brace and depth == 0:
                    return i + 1
                depth -= 1
            if c.isspace():
                i += 1
                continue
            regex_ok = c in "(,=:[!&|?{};+-*%<>~^" or source[max(0, i - 6):i + 1].endswith("return")
            i += 1
        return i

    def scan_template(i):
        chunk = i
        while i < n:
            c = source[i]
            if c == "\\":
                i += 2
                continue
            if c == "`":
                if CJK.search(source[chunk:i]):
                    out.append((chunk, i, source[chunk:i]))
                return i + 1
            if c == "$" and source.startswith("${", i):
                if CJK.search(source[chunk:i]):
                    out.append((chunk, i, source[chunk:i]))
                i = scan_code(i + 2, True)
                chunk = i
                continue
            i += 1
        return i

    scan_code(0, False)
    return out


# Key names: <kbd> text in the page and keycap / accelerator literals in the demos ("Ctrl+V").
# Named keys are translated through the "keys" map (Ctrl → Strg, Delete → Suppr …); letters,
# digits and F-keys stay as they are.
NAMED_KEYS = ("Ctrl", "Alt", "Shift", "Win", "Enter", "Esc", "Tab", "Delete", "Backspace", "Space",
              "Home", "End", "PageUp", "PageDown", "Insert")
KEY_TOKEN = r"(?:Ctrl|Alt|Shift|Win|Enter|Esc|Tab|Delete|Backspace|Space|Home|End|PageUp|PageDown|Insert|F\d{1,2}|[A-Z0-9])"
KEY_COMBO = re.compile(rf"^{KEY_TOKEN}(?:\+{KEY_TOKEN})*$")
KBD = re.compile(r"<kbd>([^<]*)</kbd>")
# Languages whose Windows keyboards print the English key names.
KEYS_AS_IS = {"en", "zh-TW", "ja", "ko"}


def map_keys(combo, keys):
    return "+".join(keys.get(tok) or tok for tok in combo.split("+"))


def key_names():
    """Named keys used by the page (<kbd>) and the demos (key literals), in a stable order."""
    page = (MANUAL / "page.html").read_text(encoding="utf-8")
    found = set()
    for m in KBD.finditer(page):
        if KEY_COMBO.match(m.group(1)):
            found.update(m.group(1).split("+"))
    for f in sorted((MANUAL / "demos").glob("*.js")):
        for body in js_ascii_literals(f.read_text(encoding="utf-8")):
            found.update(body.split("+"))
    return [k for k in NAMED_KEYS if k in found]


def js_ascii_literals(source):
    return [m.group(2) for m in re.finditer(r"(['\"])([^'\"\\\n]*)\1", source) if KEY_COMBO.match(m.group(2))
            and any(tok in NAMED_KEYS for tok in m.group(2).split("+"))]


def catalog_keys(code):
    """Key-name translations implied by the app's accelerators (粘贴\\tCtrl+V → Einfügen\\tStrg+V)."""
    path = ROOT / "locales" / f"{code}.json"
    if not path.exists():
        return {}
    out = {}
    for zh, tr in json.loads(path.read_text(encoding="utf-8")).items():
        if not isinstance(tr, str):
            continue
        a = zh.split("\t")[-1] if "\t" in zh else zh
        b = tr.split("\t")[-1] if "\t" in tr else tr
        if "+" not in a and "\t" not in zh:
            continue
        ta, tb = a.split("+"), b.split("+")
        if len(ta) == len(tb):
            for x, y in zip(ta, tb):
                x, y = x.strip(), y.strip()
                if x in NAMED_KEYS and y:
                    out.setdefault(x, y)
    return out


def source_strings():
    page = (MANUAL / "page.html").read_text(encoding="utf-8")
    blocks, attrs = page_segments(page)
    page_keys = [b[2] for b in blocks] + [a[3] for a in attrs]
    stage = {}
    for f in [MANUAL / "manual.js", *sorted((MANUAL / "demos").glob("*.js"))]:
        for _, _, body in js_literals(f.read_text(encoding="utf-8")):
            stage.setdefault(body, f.name)
    return list(dict.fromkeys(page_keys)), stage


def js_decode(body):
    try:
        return json.loads('"' + body.replace('"', '\\"').replace("\\'", "'") + '"')
    except json.JSONDecodeError:
        return body


def js_encode(text, quote):
    """Plain text -> body of a JS literal delimited by `quote` (' " or `)."""
    s = json.dumps(text, ensure_ascii=False)[1:-1]
    if quote in "'`":
        s = s.replace('\\"', '"')
    if quote == "'":
        s = s.replace("'", "\\'")
    if quote == "`":
        s = s.replace("`", "\\`").replace("${", "\\${")
    return s


def app_catalog(code):
    """zh-CN UI string -> the app's own translation (locales/<code>.json); zh-CN maps to itself."""
    path = ROOT / "locales" / f"{code}.json"
    if not path.exists():
        return {}
    cat = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for key, value in cat.items():
        if not isinstance(value, str):
            continue
        k, v = key.split("\x04")[-1], value
        out.setdefault(k, v)
        if "\t" in k and "\t" in v:      # menu text with an accelerator: the label alone
            out.setdefault(k.split("\t")[0], v.split("\t")[0])
    return out


def load(code):
    path = MANUAL / "i18n" / f"{code}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"page": {}, "stage": {}}


def prefill(code):
    page_keys, stage = source_strings()
    data = load(code)
    cat = app_catalog(code)
    added = filled = 0
    for k in page_keys:
        if k not in data["page"]:
            data["page"][k] = ""
            added += 1
    for body in stage:
        if body not in data["stage"] or not data["stage"][body]:
            text = js_decode(body)
            hit = cat.get(text, "")
            if body not in data["stage"]:
                added += 1
            data["stage"][body] = hit or data["stage"].get(body, "")
            filled += bool(hit)
    data["page"] = {k: data["page"][k] for k in page_keys}
    data["stage"] = {k: data["stage"][k] for k in stage}
    keys = data.get("keys", {})
    implied = catalog_keys(code)
    for k in key_names():
        if not keys.get(k):
            keys[k] = k if code in KEYS_AS_IS else implied.get(k, "")
            added += k not in data.get("keys", {})
    data["keys"] = {k: keys[k] for k in key_names()}
    (MANUAL / "i18n").mkdir(exist_ok=True)
    (MANUAL / "i18n" / f"{code}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"{code}: {len(page_keys)} page + {len(stage)} stage strings; {added} keys added, {filled} prefilled from locales/{code}.json")


def check(codes):
    page_keys, stage = source_strings()
    problems = []
    for code in codes:
        data = load(code)
        mp = [k for k in page_keys if not data["page"].get(k)]
        ms = [k for k in stage if not data["stage"].get(k)]
        names = key_names()
        mk = [k for k in names if not data.get("keys", {}).get(k)]
        extra = (set(data["page"]) - set(page_keys)) | (set(data["stage"]) - set(stage))
        print(f"{code}: page {len(page_keys) - len(mp)}/{len(page_keys)}, stage {len(stage) - len(ms)}/{len(stage)}, "
              f"keys {len(names) - len(mk)}/{len(names)}" + (f", {len(extra)} stale keys" if extra else ""))
        if mp or ms or mk:
            problems.append(code)
    return problems


def translate_page(source, data):
    blocks, attrs = page_segments(source)
    edits = [(s, e, data["page"].get(text) or text) for s, e, text in blocks]
    for ts, te, name, value in attrs:
        tr = data["page"].get(value) or value
        tag = source[ts:te]
        edits.append((ts, te, tag.replace(f'{name}="{html.escape(value, quote=True)}"',
                                          f'{name}="{html.escape(tr, quote=True)}"')
                                  .replace(f'{name}="{value}"', f'{name}="{html.escape(tr, quote=True)}"')))
    for s, e, text in sorted(edits, key=lambda x: -x[0]):
        source = source[:s] + text + source[e:]
    keys = data.get("keys") or {}
    if keys:
        source = KBD.sub(lambda m: f"<kbd>{map_keys(m.group(1), keys)}</kbd>"
                         if KEY_COMBO.match(m.group(1)) else m.group(0), source)
    return source


def translate_js(source, data, key_literals=False):
    """Stage values are plain text; they are escaped for the literal's own quotes. With
    `key_literals` (the demos, never the engine, whose 'Enter' is event logic) key-name
    literals such as 'Ctrl+V' go through the "keys" map too."""
    for s, e, body in sorted(js_literals(source), key=lambda x: -x[0]):
        tr = data["stage"].get(body)
        if tr:
            quote = source[s - 1]
            if quote == "}":          # a template chunk right after ${...}
                quote = "`"
            source = source[:s] + js_encode(tr, quote) + source[e:]
    keys = data.get("keys") or {}
    if key_literals and keys:
        def swap(m):
            body = m.group(2)
            if KEY_COMBO.match(body) and any(tok in NAMED_KEYS for tok in body.split("+")):
                return m.group(1) + js_encode(map_keys(body, keys), m.group(1)) + m.group(1)
            return m.group(0)
        source = re.sub(r"(['\"])([^'\"\\\n]*)\1", swap, source)
    return source


def build(out, code, data, chrome):
    """Write one language's manual into `out` (a directory). `chrome(page) -> page` fills the
    <!--manual:*--> placeholders (see fill)."""
    out = Path(out).resolve()
    if not any(out.is_relative_to(ROOT / d) and out != ROOT / d for d in (".cache", "dist")):
        raise SystemExit(f"Refusing to write the manual outside .cache/ or dist/: {out}")
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(MANUAL / "assets", out / "assets")
    (out / "demos").mkdir(parents=True)
    shutil.copy2(MANUAL / "manual.css", out / "manual.css")
    for f in [MANUAL / "manual.js", *sorted((MANUAL / "demos").glob("*"))]:
        target = out / ("manual.js" if f.name == "manual.js" else f"demos/{f.name}")
        if f.suffix == ".js":
            target.write_text(translate_js(f.read_text(encoding="utf-8"), data, key_literals=f.name != "manual.js"),
                              encoding="utf-8", newline="\n")
        else:
            shutil.copy2(f, target)
    page = translate_page((MANUAL / "page.html").read_text(encoding="utf-8"), data)
    page = page.replace('<html lang="zh-CN">', f'<html lang="{code}">', 1)
    # Content hashes on the page's scripts and stylesheets: the CDN lets browsers keep them for
    # hours, and a cached older script must never run with a newer page.
    page = re.sub(r'\b(href|src)="((?:demos/)?[\w.-]+\.(?:css|js))"', lambda m: (
        f'{m.group(1)}="{m.group(2)}?v={hashlib.sha256((out / m.group(2)).read_bytes()).hexdigest()[:10]}"'), page)
    (out / "index.html").write_text(chrome(page), encoding="utf-8", newline="\n")


def fill(parts):
    """chrome(page) for build: the page's <!--manual:head-->, <!--manual:header--> and
    <!--manual:footer--> become parts["head"] ... (build-site.py passes the site's header
    and footer; a preview leaves them empty)."""
    def chrome(page):
        for name in ("head", "header", "footer"):
            mark = f"<!--manual:{name}-->"
            if mark not in page:
                raise SystemExit(f"site/manual/page.html has no {mark}")
            page = page.replace(mark, parts.get(name, ""))
        return page
    return chrome


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", action="store_true", help="print counts and write i18n/_source.json")
    ap.add_argument("--prefill", nargs="*", metavar="LANG")
    ap.add_argument("--check", nargs="*", metavar="LANG")
    ap.add_argument("--build", metavar="LANG", help="preview one language into --out")
    ap.add_argument("--out", default=None, help="preview directory (default .cache/manual-build/<LANG>)")
    args = ap.parse_args()
    if args.build:
        out = Path(args.out) if args.out else ROOT / ".cache" / "manual-build" / args.build
        data = {"page": {}, "stage": {}} if args.build == "zh-CN" else load(args.build)
        build(out.resolve(), args.build, data, fill({}))
        print(f"built {args.build} manual into {out}")
    if args.source:
        page_keys, stage = source_strings()
        (MANUAL / "i18n").mkdir(exist_ok=True)
        (MANUAL / "i18n" / "_source.json").write_text(json.dumps(
            {"page": page_keys, "stage": stage}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(f"{len(page_keys)} page strings, {len(stage)} stage strings")
    if args.prefill is not None:
        for code in args.prefill:
            prefill(code)
    if args.check is not None:
        codes = args.check or [p.stem for p in sorted((MANUAL / "i18n").glob("*.json")) if not p.stem.startswith("_")]
        if check(codes):
            sys.exit(1)


if __name__ == "__main__":
    main()
