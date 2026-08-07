
import re
from pathlib import Path
STATIC = Path("/home/amr/apps/mlt-pipeline/open_edit/serve/static")
BACKUP = sorted(Path("/home/amr/apps/mlt-pipeline/open_edit/serve").glob("static.bak.ui2_before.*"))[-1]
EMOJI_PAT = re.compile(
    "[\U0001F000-\U0001FAFF\u2600-\u27BF\u2190-\u21FF\u2B00-\u2BFF\uFE0F\u2705\u274C\u26A0\u2699\u23E9\u23EA\u23ED\u23EE\u23EF\u23F8\u23F9\u23FA\u2795\u2796\u2716\u2728]"
)
def audit_static():
    out = []
    emoji = {}
    for f in sorted(STATIC.rglob("*")):
        if f.suffix not in (".js", ".html", ".css"):
            continue
        t = f.read_text(encoding="utf-8", errors="ignore")
        found = [(m.group(0), t[:m.start()].count("\n") + 1) for m in EMOJI_PAT.finditer(t)]
        if found:
            emoji[str(f.relative_to(STATIC))] = found
    out.append(f"emoji total: {sum(len(v) for v in emoji.values())} -> { {k: len(v) for k, v in emoji.items()} }")
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    out.append(f"css braces: {css.count('{')}/{css.count('}')} balanced={css.count('{')==css.count('}')}")
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    void = {"br","img","input","meta","link","hr","area","base","col","embed","source","track","wbr","path","circle","rect","line","polygon","polyline","svg"}
    stack = []
    for m in re.finditer(r"<(/?)([a-zA-Z][a-zA-Z0-9-]*)", html):
        close, name = m.group(1), m.group(2)
        if close:
            if stack and stack[-1] == name: stack.pop()
        elif name not in void: stack.append(name)
    out.append(f"html unclosed: {len(stack)} {stack[-6:]}")
    appjs = (STATIC / "app.js").read_text(encoding="utf-8")
    c = {
        "has 640x360 label": "Review artifact · 640×360" in appjs,
        "no Proxy 720p": "Proxy 720p" not in appjs,
        "no 540p": "540p" not in appjs,
        "Source media": "Source media" in appjs or "Source media" in html,
    }
    out.append(f"contracts: {c}")
    changed = []
    for f in sorted(STATIC.rglob("*")):
        if not f.is_file(): continue
        rel = f.relative_to(STATIC)
        b = BACKUP / rel
        if b.exists() and f.read_bytes() != b.read_bytes():
            changed.append(str(rel))
        elif not b.exists():
            changed.append(str(rel) + " (new)")
    out.append(f"changed vs backup: {len(changed)} {changed}")
    return "\n".join(out)
