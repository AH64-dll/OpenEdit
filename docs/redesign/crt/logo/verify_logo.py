#!/usr/bin/env python3
"""Verification for the CRT logo deliverable (docs/redesign/crt/logo/).

Checks, against the LIVE app source (open_edit/serve/static/):
  1. snippet keeps every contract the JS/HTML around the logo relies on
  2. no JS in the app queries the logo region (zero coupling)
  3. crt_logo.css is self-contained (no url(), @import, fonts)
  4. theme coverage (dark-first + [data-theme="light"] overrides)
  5. demo.html embeds the IDENTICAL logo markup as the snippet
  6. screenshots exist and are non-trivial in size

Run:  .venv/bin/python docs/redesign/crt/logo/verify_logo.py   (or any python3)
"""
import re
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent
REPO = ROOT.parents[3]                      # mlt-pipeline
STATIC = REPO / "open_edit" / "serve" / "static"

ok = True
def check(cond, msg):
    global ok
    print(("PASS  " if cond else "FAIL  ") + msg)
    ok = ok and cond

snip = (ROOT / "crt_logo_snippet.html").read_text(encoding="utf-8")
css  = (ROOT / "crt_logo.css").read_text(encoding="utf-8")
demo = (ROOT / "demo.html").read_text(encoding="utf-8")
index = (STATIC / "index.html").read_text(encoding="utf-8")

print("== 1. snippet contract ==")
check('<span class="logo" data-od-id="logo">' in snip, "snippet keeps <span class=\"logo\" data-od-id=\"logo\">")
check('class="logo-badge crt-logo"' in snip, "snippet keeps .logo-badge (extended with .crt-logo)")
real_markup = snip.split('-->', 1)[1]
check(real_markup.count('data-od-id=') == 1, "exactly one data-od-id in snippet markup (logo)")
check('Open&nbsp;Edit' in snip, "wordmark text 'Open&nbsp;Edit' intact")
check('crt-logo-svg' in snip and 'crt-logo-scanlines' in snip and 'crt-logo-vignette' in snip,
      "svg + scanline + vignette layers present")

print("== 2. JS coupling (app.js + js/*.js) ==")
hits = []
for jf in sorted((STATIC / "js").glob("*.js")) + [STATIC / "app.js"]:
    text = jf.read_text(encoding="utf-8")
    for m in re.finditer(r'logo', text, re.I):
        hits.append((jf.name, m.start(), text[max(0, m.start()-40):m.start()+40]))
check(not hits, "no JS reference to the logo region (zero JS deps)")
for h in hits:
    print("       (context) %s @%d: %r" % h)

print("== 3. crt_logo.css self-contained ==")
def strip_comments(text):
    return re.sub(r'/\*.*?\*/', '', text, flags=re.S)
css_code = strip_comments(css)
check('url(' not in css_code, "no url() references (comments excluded)")
check('@import' not in css_code, "no @import")
check('@font-face' not in css, "no embedded fonts")
check('var(--accent)' in css and 'var(--green)' in css,
      "inherits app tokens (--accent / --green)")
check('fill: radial-gradient' not in css_code and 'mask-image:' in css_code,
      "wash uses CSS mask (gradient fill on SVG elements is unreliable in Chrome)")

print("== 4. theme coverage ==")
check('[data-theme="light"] .logo .logo-badge.crt-logo' in css, "light-theme override block present")
check('prefers-reduced-motion' in css, "prefers-reduced-motion handling present")
check('@keyframes crt-flicker' in css and 'steps(1, end)' in css, "low-fps flicker keyframes present")
check('--crt-size' in css, "size knob (--crt-size) present")

print("== 5. demo uses identical markup ==")
def logo_span_of(text):
    after = text.split("-->", 1)[-1] if "CONTRACT PRESERVED" in text else text
    m = re.search(r'<span class="logo" data-od-id="logo">.*?Open&nbsp;Edit\s*</span>', after, re.S)
    return re.sub(r'\s+', " ", m.group(0)) if m else ""
check(logo_span_of(snip) == logo_span_of(demo), "demo.html logo markup == snippet logo markup")
demo_norm = re.sub(r'\s+', ' ', demo)
check(demo_norm.count(logo_span_of(demo)) == 6, "logo span appears 6x in demo (h1, 2 topbars, 2 big, template)")

print("== 6. screenshots ==")
for name in ("logo_dark.png", "logo_light.png"):
    p = ROOT / name
    check(p.exists() and p.stat().st_size > 20000, "%s exists and non-trivial (%s bytes)" % (name, p.stat().st_size if p.exists() else 0))

print()
sys.exit(0 if ok else 1)
