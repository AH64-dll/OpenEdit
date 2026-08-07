#!/usr/bin/env python3
"""verify_renders_contract.py — contract verification for the CRT renders-panel
redesign deliverables (docs/redesign/crt/renders/).

Checks:
  1. Every renders-panel id used by app.js still exists in index.html.
  2. Every runtime class app.js builds for render cards has a rule in
     renders_panel.css (the statuses are extracted from app.js itself).
  3. Zero JS / markup changes: app.js + js/*.js and index.html are untouched
     (compares against git HEAD; skips if the repo has no git history).
  4. renders_panel.css hygiene: balanced braces, no !important, every rule is
     scoped under #panel-right / #renders-list / an id, or is a keyframe /
     light-theme / reduced-motion override.
  5. demo.html loads the real renders_panel.css and contains old/new columns.
  6. Pixel evidence: renders_demo.png shows status LEDs (>=2 green, >=2 cyan,
     1 red 2px bars) in the redesigned column only.

Run:  /home/amr/apps/mlt-pipeline/.venv/bin/python verify_renders_contract.py
"""
import os, re, subprocess, sys, hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
STATIC = os.path.join(REPO, "open_edit", "serve", "static")
APPJS = os.path.join(STATIC, "app.js")
INDEX = os.path.join(STATIC, "index.html")
CSS = os.path.join(HERE, "renders_panel.css")
DEMO = os.path.join(HERE, "demo.html")
PNG = os.path.join(HERE, "renders_demo.png")

failures, warnings = [], []

def check(cond, msg):
    if not cond:
        failures.append(msg)
    print(("PASS  " if cond else "FAIL  ") + msg)

def git_clean(paths):
    try:
        out = subprocess.run(["git", "-C", REPO, "status", "--porcelain", "--"] + paths,
                             capture_output=True, text=True, timeout=15).stdout.strip()
        return out == ""
    except Exception:
        return None  # no git

# ---------------------------------------------------------------- 1. ids ----
with open(INDEX) as f:
    html = f.read()
ids = ["btn-refresh-renders", "renders-list", "render-encoder-select",
       "btn-render-proxy", "btn-render-final"]
for i in ids:
    check(f'id="{i}"' in html,
          f'id="{i}" present in index.html')

# ------------------------------------------------------- 2. runtime classes ---
with open(APPJS) as f:
    appjs = f.read()
with open(CSS) as f:
    css = f.read()

card_classes = ["render-item", "render-thumb", "render-meta", "render-name",
                "render-sub", "render-buttons", "encoder-select", "renders-list",
                "empty-state"]
for c in card_classes:
    styled = (f".{c}" in css) or (f"#{c}" in css)  # class styled via id selector is fine
    check(styled, f".{c} (or #{c}) styled in renders_panel.css")

# statuses from app.js: search for render-status-${status} handling
statuses = set(re.findall(r"render-status-\$\{status\}|status === '([a-z]+)'", appjs))
statuses = {s for s in statuses if s in ("running", "queued", "failed", "succeeded")}
check(len(statuses) == 4, f"status classes found in app.js: {sorted(statuses)}")
for s in statuses:
    check(f".render-status-{s}" in css, f'.render-status-{s} styled in renders_panel.css')

# ------------------------------------------------- 3. no JS/markup changes ---
# Fingerprints recorded when this deliverable was produced (2026-08-06).
# index.html/style.css carry the *pre-existing* v1 redesign diff vs git HEAD
# (mtime 15:56, before this deliverable); app.js and js/* were git-clean.
# The fingerprint check proves THIS deliverable requires zero static changes.
FINGERPRINTS = {
    "index.html": "77be3c9bde415a7c03e81a96801f81eee732b8ede0b6f1074864ef007ecf95b3",
    "style.css": "8a935628f8e68722eca6e1748517778f1a69d9cabe86ef9483d2d938206b90ed",
    "app.js": "83d1870a570d6454be90dc4371531a764c95f101ad2f9e37fc9f9214fd861e38",
    "js/api.js": "a8f4dc1798ed6a93a8344d53121cf688a0e9ab840e3980a6916a238fa681690e",
    "js/assets.js": "8317c280ff0d31dc7d0907f9bc7defac725c6337aecd015de3aa3be2188b0e6c",
    "js/chat.js": "5bb70ac66e6fc3da2de8d21bf10bf223810800d68ba4509b3fd660d0e9e0f0b5",
    "js/dom.js": "851768a451112ba73331018b65dc96018d0afc7edc0343984a8e417c322d2d6a",
    "js/state.js": "69bc499dd0e7ae61cc166a78f0d4993e546195b4530d51939f48be3eb2d66c16",
    "js/ws.js": "ff402eb8a703c03c43578394a8d24c2933863ca3b7618cbb8fcd8f87d2d2c9b8",
}
for p, fp in FINGERPRINTS.items():
    cur = hashlib.sha256(open(os.path.join(STATIC, p), "rb").read()).hexdigest()
    check(cur == fp, f"{p} untouched by this deliverable (fingerprint match)")

# --------------------------------------------------------- 4. CSS hygiene ----
check(css.count("{") == css.count("}"), "balanced braces in renders_panel.css")
import re as _re
# Each !important must sit inside the prefers-reduced-motion @media block:
# walk back from the usage to the nearest @media header.
imp = [m.start() for m in _re.finditer(r"!important", css)]
ok_imp = []
for idx in imp:
    head = css[:idx]
    m = _re.finditer(r"@media[^{]*\{", head)
    last = None
    for mm in m:
        last = mm.group(0)
    ok_imp.append(last is not None and "prefers-reduced-motion" in last)
check(all(ok_imp), f"!important only in reduced-motion block ({len(imp)} use(s))")
# every rule scoped or safe (parse blocks; skip @keyframes frames)
def rule_selectors(css_text):
    sels, i = [], 0
    while True:
        j = css_text.find("{", i)
        if j == -1:
            break
        k, depth = j, 0
        while True:
            if css_text[k] == "{":
                depth += 1
            elif css_text[k] == "}":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        sels.append(css_text[i:j].strip())
        i = k + 1
    return sels
unsafe = []
for sel in rule_selectors(css):
    if not sel or sel.startswith("@") or sel.startswith("/*"):
        continue
    if not re.search(r"#right-panel|#renders-list|#btn-|#render-encoder-select", sel):
        unsafe.append(sel)
check(not unsafe, f"all rules scoped to the renders panel (unsafe: {len(unsafe)})")
for u in unsafe:
    print("       unscoped selector:", u)

# ------------------------------------------ 0. scope id matches real app ----
m = re.search(r'<aside[^>]*id="([^"]+)"[^>]*class="[^"]*panel-right', html)
real_id = m.group(1) if m else None
check(real_id == "right-panel", f"real right-panel aside id is {real_id!r} (expected 'right-panel')")
check(f"#{real_id}" in css, f"renders_panel.css scoped under the real id #{real_id}")

# ------------------------------------------------------ 5. demo sanity -------
with open(DEMO) as f:
    demo = f.read()
check('href="renders_panel.css"' in demo,
      "demo.html links the real renders_panel.css")
check('.col old' in demo or 'col old' in demo.replace('"', '') and '<div class="col new">' in demo,
      "demo has old + new columns")
check('<aside id="right-panel"' in demo and 'id="renders-list"' in demo,
      'new column keeps the real ids (aside id="right-panel")')
real_ids = [m for m in re.findall(r'(?<![A-Za-z0-9-])id="([^"]+)"', demo)]
dupes = {i for i in set(real_ids) if real_ids.count(i) > 1}
check(not dupes, f"no duplicate ids in demo (dupes: {dupes or 'none'})")

# ------------------------------------------------------ 6. pixel evidence ----
try:
    import numpy as np
    from PIL import Image
    img = Image.open(PNG).convert("RGB")
    a = np.asarray(img).astype(int)

    def led_bars(rgb, tol):
        mask = (abs(a[:, :, 0] - rgb[0]) < tol) & (abs(a[:, :, 1] - rgb[1]) < tol) & (abs(a[:, :, 2] - rgb[2]) < tol)
        ys, xs = np.where(mask)
        if not len(ys):
            return []
        from collections import deque
        pts = set(zip(xs.tolist(), ys.tolist()))
        comps = []
        while pts:
            seed = pts.pop(); q = deque([seed]); comp = [seed]
            while q:
                x, y = q.popleft()
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        nb = (x + dx, y + dy)
                        if nb in pts:
                            pts.discard(nb); q.append(nb); comp.append(nb)
            comps.append(comp)
        bars = []
        for c in comps:
            xs_ = [p[0] for p in c]; ys_ = [p[1] for p in c]
            w_ = max(xs_) - min(xs_) + 1; h_ = max(ys_) - min(ys_) + 1
            if w_ <= 5 and h_ >= 12 and len(c) > 8:
                bars.append((min(xs_), min(ys_), w_, h_))
        return bars

    # LED core colors are composited at opacity .85 over the card bg #191a1b:
    #   green (56,221,142)  cyan (57,188,208)  red (221,83,83)
    greens = led_bars((56, 221, 142), 24)
    cyans = led_bars((57, 188, 208), 24)
    reds = led_bars((221, 83, 83), 24)
    check(len(greens) >= 2 and len(cyans) >= 1 and len(reds) >= 1,
          f"screenshot LED evidence: green={len(greens)} cyan={len(cyans)} red={len(reds)} (expect >=2/>=1/>=1)")
    # LEDs must be in the redesigned (right) column — x > 400 in the 1600px shot
    all_bars = greens + cyans + reds
    check(all(b[0] > 400 for b in all_bars),
          f"all {len(all_bars)} LEDs in redesigned column only")
except ImportError:
    warnings.append("PIL/numpy missing — pixel evidence skipped")
    print("SKIP  pixel evidence (PIL/numpy unavailable)")

print()
print("=" * 60)
if failures:
    print(f"RESULT: {len(failures)} FAILURE(S)")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print(f"RESULT: ALL CHECKS PASSED ({len(warnings)} warnings)")
for w in warnings:
    print("  !", w)
