#!/usr/bin/env python3
"""build_demo.py — builds demo.html (old renders panel vs CRT redesign).

Extracts the CURRENT renders/panel/button CSS rules verbatim from
open_edit/serve/static/style.css for the "old" column, and links the real
renders_panel.css for the "new" column, so the demo always mirrors the
actual shipped rules. Run from anywhere:

    /home/amr/apps/mlt-pipeline/.venv/bin/python build_demo.py
"""
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))  # docs/redesign/crt/renders -> repo root
STATIC = os.path.join(REPO, "open_edit", "serve", "static")

def extract_rules(css, needles):
    """Return full CSS rules whose selector contains any needle, in order."""
    out, i = [], 0
    while True:
        j = css.find("{", i)
        if j == -1:
            break
        k, depth = j, 0
        while True:
            if css[k] == "{":
                depth += 1
            elif css[k] == "}":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        sel = css[i:j].strip()
        if any(n in sel for n in needles):
            out.append(f"{sel} {{\n{css[j+1:k]}\n}}")
        i = k + 1
    return out

def grab_block(css, sel):
    m = re.search(re.escape(sel) + r"\s*\{", css)
    if not m:
        raise SystemExit(f"block not found: {sel}")
    j = m.start()
    k, depth = j, 0
    while True:
        if css[k] == "{":
            depth += 1
        elif css[k] == "}":
            depth -= 1
            if depth == 0:
                break
        k += 1
    return css[j:k+1]

def main():
    with open(os.path.join(STATIC, "style.css")) as f:
        css = f.read()

    needles = [
        ".panel-section", ".panel-right", ".renders-list", ".render-item",
        ".render-thumb", ".render-meta", ".render-name", ".render-sub",
        ".render-buttons", ".encoder-select", ".empty-state", ".muted",
        ".small", ".btn", ".icon-svg", ".panel {",
    ]
    old_rules = extract_rules(css, needles)
    root_dark = grab_block(css, ":root")
    root_light = grab_block(css, '[data-theme="light"]')

    panel_new = PANEL.format(cards=CARDS, actions=ACTIONS)
    # Old column: identical markup but WITHOUT the ids, so the new CSS
    # (scoped to #right-panel / #renders-list / #btn-*) cannot touch it
    # and the page has no duplicate ids.
    panel_old = panel_new
    for i in ["renders-list", "btn-refresh-renders", "render-encoder-select",
              "btn-render-proxy", "btn-render-final"]:
        panel_old = panel_old.replace(f' id="{i}"', "")

    demo = DEMO_TEMPLATE.format(
        root_dark=root_dark,
        root_light=root_light,
        old_rules="\n".join(old_rules),
        PANEL_OLD=panel_old,
        PANEL_NEW=panel_new,
    )
    out = os.path.join(HERE, "demo.html")
    with open(out, "w") as f:
        f.write(demo)
    print(f"wrote {out} ({len(demo)} bytes; {len(old_rules)} old rules extracted)")

# ---------------------------------------------------------------- template ---

CARDS = """\
          <div class="render-item render-status-succeeded" role="button" tabindex="0">
            <div class="render-thumb">\U0001F39E\uFE0F</div>
            <div class="render-meta">
              <div class="render-name">review_v3_proxy.mp4</div>
              <div class="render-sub">Review artifact &middot; 640&times;360 &middot; Ready &middot; 24.6 MB &middot; 8/6/2026, 4:12:03 PM</div>
            </div>
          </div>
          <div class="render-item render-status-succeeded" role="button" tabindex="0">
            <div class="render-thumb">\U0001F39E\uFE0F</div>
            <div class="render-meta">
              <div class="render-name">final_cut_1080p.mp4</div>
              <div class="render-sub">Final export &middot; 1080p &middot; Ready &middot; 124.8 MB &middot; 8/6/2026, 4:15:47 PM</div>
            </div>
          </div>
          <div class="render-item render-status-running" role="button" tabindex="0">
            <div class="render-thumb">\u23F3</div>
            <div class="render-meta">
              <div class="render-name">review_v4_proxy.mp4</div>
              <div class="render-sub">Review artifact &middot; 640&times;360 &middot; Rendering&hellip; &middot; &mdash; &middot; 8/6/2026, 4:18:02 PM</div>
            </div>
          </div>
          <div class="render-item render-status-queued" role="button" tabindex="0">
            <div class="render-thumb">\U0001F39E\uFE0F</div>
            <div class="render-meta">
              <div class="render-name">final_alt_2k.mp4</div>
              <div class="render-sub">Final export &middot; 1080p &middot; Queued &middot; &mdash; &middot; 8/6/2026, 4:18:05 PM</div>
            </div>
          </div>
          <div class="render-item render-status-failed" role="button" tabindex="0">
            <div class="render-thumb">\U0001F39E\uFE0F</div>
            <div class="render-meta">
              <div class="render-name">final_v2_4k.mp4</div>
              <div class="render-sub">Final export &middot; 1080p &middot; Failed: ffmpeg exit code 1 &mdash; encoder &rsquo;nvenc&rsquo; not found on this GPU (CUDA 12.4), x264 fallback unavailable &middot; 8/6/2026, 3:58:41 PM</div>
            </div>
          </div>"""

ACTIONS = """\
          <div class="render-buttons">
            <label class="encoder-select muted small" title="GPU uses NVENC when available; CPU uses software x264">
              Encoder
              <select id="render-encoder-select">
                <option value="gpu" selected>GPU (default)</option>
                <option value="cpu">CPU</option>
              </select>
            </label>
            <button id="btn-render-proxy" class="btn btn-secondary btn-sm" data-od-id="btn-render-proxy">Render proxy</button>
            <button id="btn-render-final" class="btn btn-secondary btn-sm" data-od-id="btn-render-final">Render final</button>
          </div>"""

PANEL = """\
        <div class="panel-section">
          <div class="panel-section-header">
            <span>Renders</span>
            <button id="btn-refresh-renders" class="btn btn-ghost btn-xs" title="Refresh" data-od-id="btn-refresh-renders">
              <svg class="icon-svg" viewBox="0 0 24 24"><path d="M23 4v6h-6M1 20v-6h6"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/></svg>
            </button>
          </div>
          <div id="renders-list" class="renders-list">
{cards}
          </div>
{actions}
        </div>"""

DEMO_TEMPLATE = """<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Renders panel — v1 vs CRT redesign (demo)</title>
<link rel="stylesheet" href="renders_panel.css">
<style>
  /* ===== base palette copied verbatim from open_edit/serve/static/style.css ===== */
  {root_dark}
  {root_light}

  /* ===== demo chrome (not part of the app) ===== */
  * {{ box-sizing: border-box; }}
  body {{ background: #060708; margin: 0; padding: 28px 24px 40px; font-family: 'Inter', -apple-system, 'Segoe UI', Roboto, sans-serif; color: #d7dbe3; }}
  h1 {{ font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 15px; letter-spacing: .08em; color: #3dffa2; margin: 0 0 4px; text-transform: uppercase; }}
  .sub {{ font-size: 12px; color: #8a8f98; margin: 0 0 18px; max-width: 1100px; line-height: 1.6; }}
  .sub code {{ color: #3fd9f0; font-family: 'JetBrains Mono', monospace; font-size: 11px; }}
  .toolbar {{ display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }}
  #theme-toggle {{ font-family: 'JetBrains Mono', monospace; font-size: 11px; padding: 5px 12px; border-radius: 6px; border: 1px solid rgba(255,255,255,.15); background: rgba(255,255,255,.04); color: #d7dbe3; cursor: pointer; }}
  #theme-toggle:hover {{ border-color: #3dffa2; color: #3dffa2; }}
  .compare {{ display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 22px; max-width: 900px; }}
  .col {{ min-width: 0; }}
  .col h2 {{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .appwin {{ min-width: 0; }}
  @media (max-width: 900px) {{ .compare {{ grid-template-columns: 1fr; }} }}
  .col {{ display: flex; flex-direction: column; gap: 10px; }}
  .col h2 {{ font-family: 'JetBrains Mono', monospace; font-size: 11px; letter-spacing: .12em; text-transform: uppercase; margin: 0; padding: 6px 10px; border-radius: 6px 6px 0 0; }}
  .col.old h2 {{ color: #ff8a8a; background: rgba(255,93,93,.08); border: 1px solid rgba(255,93,93,.25); border-bottom: none; }}
  .col.new h2 {{ color: #3dffa2; background: rgba(61,255,162,.07); border: 1px solid rgba(61,255,162,.28); border-bottom: none; }}
  .col.old h2::after {{ content: "  (style.css rules, unmodified)"; font-size: 9.5px; color: #8a8f98; text-transform: none; letter-spacing: 0; }}
  .col.new h2::after {{ content: "  (style.css + renders_panel.css)"; font-size: 9.5px; color: #8a8f98; text-transform: none; letter-spacing: 0; }}

  /* ===== app window frame ===== */
  .appwin {{ background: var(--bg); border: 1px solid var(--border); border-radius: 0 8px 8px 8px; overflow: hidden; box-shadow: 0 18px 50px rgba(0,0,0,.5); }}
  .appwin .titlebar {{ display: flex; align-items: center; gap: 6px; padding: 6px 10px; border-bottom: 1px solid var(--border); font-size: 10px; color: var(--text-dim); font-family: 'JetBrains Mono', monospace; letter-spacing: .05em; }}
  .appwin .titlebar i {{ width: 8px; height: 8px; border-radius: 50%; display: inline-block; }}
  .appwin .titlebar i:nth-child(1) {{ background: #ff5d5d; }} .appwin .titlebar i:nth-child(2) {{ background: #ffc857; }} .appwin .titlebar i:nth-child(3) {{ background: #3dffa2; }}
  .appwin .panel {{ height: 640px; width: 380px; margin: 0 auto; }}

  /* ===== caption under each window ===== */
  .legend {{ font-size: 10.5px; color: #8a8f98; line-height: 1.65; padding: 0 4px; }}
  .legend b {{ color: #3dffa2; font-weight: 600; }}
  .legend s {{ color: #ff8a8a; }}

  /* old-side faithful rules extracted from style.css (see build_demo.py) */
  {old_rules}

  /* keep the two demo windows from inheriting each other's list scroll */
  .appwin .panel-section {{ min-height: 0; }}
</style>
</head>
<body>

<h1>Renders panel &mdash; v1 vs CRT redesign</h1>
<p class="sub">
  Same DOM, same ids/classes, same JS. Left: current <code>style.css</code> rules, untouched.
  Right: the same markup after appending <code>renders_panel.css</code> (this demo loads the real file).
  Kept: name, mode, status icon+label, click-to-load. Removed/softened: 34px emoji thumb, noisy
  size/timestamp tail, full-width buttons, unbounded list. Cards: status LED + phosphor glow
  (succeeded = phosphor green, running/queued = cyan, failed = red).
</p>

<div class="toolbar">
  <button id="theme-toggle" type="button">Toggle light theme</button>
  <span class="sub" style="margin:0">dark-first &mdash; <code>[data-theme=&quot;light&quot;]</code> overrides ship in the same CSS file</span>
</div>

<div class="compare">
  <div class="col old">
    <h2>v1 &mdash; current</h2>
    <div class="appwin">
      <div class="titlebar"><i></i><i></i><i></i>&nbsp; Review Studio &mdash; right panel (renders)</div>
      <aside class="panel panel-right">
{PANEL_OLD}
      </aside>
    </div>
    <div class="legend">
      <b>Kept:</b> name, mode&middot;status line, click-to-load. &nbsp;<s>Noise:</s> 34px emoji tile, long
      meta line (size, timestamp), 110px-min full-width buttons, list can push Notes/Style out of view.
    </div>
  </div>

  <div class="col new">
    <h2>CRT redesign</h2>
    <div class="appwin">
      <div class="titlebar"><i></i><i></i><i></i>&nbsp; Review Studio &mdash; right panel (renders)</div>
      <aside id="right-panel" class="panel panel-right">
{PANEL_NEW}
      </aside>
    </div>
    <div class="legend">
      <b>Kept:</b> render name (mono), mode + status, click-to-load preview, encoder + proxy/final
      actions, refresh. &nbsp;<b>Removed/softened:</b> oversized thumb &rarr; 26px status-tinted tile;
      size/timestamp &rarr; truncated to one dim mono line; buttons &rarr; compact cyan/green;
      list &rarr; internal scroll. Status color coding: succeeded=phosphor green, running/queued=cyan,
      failed=red (LED + border + hover glow).
    </div>
  </div>
</div>

<script>
  // ?theme=light (or =dark) presets the theme for headless screenshots.
  const q = new URLSearchParams(location.search).get('theme');
  if (q === 'light' || q === 'dark') document.documentElement.setAttribute('data-theme', q);
  document.getElementById('theme-toggle').addEventListener('click', () => {{
    const r = document.documentElement;
    r.setAttribute('data-theme', r.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');
  }});
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
