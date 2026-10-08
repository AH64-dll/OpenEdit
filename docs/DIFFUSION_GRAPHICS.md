# Diffusion graphics and timing

SQLite is authoritative. The optional browser worker renders a literal JSX
composition into checked CAS media. Existing MLT/FFmpeg, HyperFrames and legacy
Remotion backends continue to consume the operation graph.

## Install

Use Node 24, npm, full FFmpeg/ffprobe and the Python environment running OpenEdit:

```bash
python -m open_edit.integrations.diffusion.setup --graphics --chromium
open_edit serve --review-only
```

On Linux, install Chromium's system libraries using the packaged Playwright
CLI: `node open_edit/integrations/diffusion/browser/node_modules/playwright-core/cli.js install --with-deps chromium`.
In an installed wheel, substitute its package path. Optional setup is explicit;
MCP startup and ordinary Python edits never install or start Node/Chromium.

The browser package has its own exact lockfile. Runtime, reconciler, encoder,
asset and JSX source are pinned to Diffusion commit
`fefcde9df7198466bd7cc9f3a9d7eae1575b5b12`, unchanged under MPL-2.0.
The host is MIT; bundled Noto Sans Regular is SIL OFL-1.1. Sources, locks,
provenance and licenses ship in wheels and source distributions; installed
node_modules and browser downloads do not.

For a read-only Python installation, copy both sibling `worker` and `browser`
directories into a writable directory and set `OPEN_EDIT_DIFFUSION_WORKER_DIR`
and `OPEN_EDIT_DIFFUSION_BROWSER_DIR` accordingly. The graphics compiler uses
the pinned source-writer files in its sibling `worker/vendor` directory.
`OPEN_EDIT_CHROMIUM` can select an existing compatible Chromium executable;
its version contributes to the cache key. CI sets
`OPEN_EDIT_CHROMIUM_NO_SANDBOX=1` for its isolated runners; normal launches keep
Chromium's sandbox.

## Studio workflow

Open **Graphics studio** below the preview. Edit the JSX, select a layer and
change its properties, or drag a direct scene child on the canvas. Canvas
placement is evaluated at frame zero; nested elements remain editable through
their parent-relative properties/source. The pinned source writer changes the
same JSX shown in the code pane.

Group sizes come from their children, so group width/height controls are disabled.
Keyframed properties remain editable in JSX; their numeric controls and animated
position dragging are disabled to preserve the animation.

Choose **Render preview**, inspect the transparent preview or play its
animation, then **Add to timeline**. Updating an existing graphics clip retains
its placement, effects and explicit trims. A full-source clip follows the new
render duration. An update that would erase an explicit trim or overlap another
clip is rejected. An unchanged update is a graph no-op.

Drafts survive tab reloads in session storage. Compile/render/QC failures keep
the last successful preview. Cancel stops the managed browser/encoder process
tree; a later preview starts a fresh worker. Other editors' writes retain your
draft and disable applying it. **Reload source** explicitly discards the draft;
copy intended changes before reloading and reapply them to the current revision.

## Same six MCP tools

1. `query_project` with `query=get_graphics_view`, optional `clip_id`, and
   `params.include_source=true` returns a source document and `graph_revision`.
   Omit `include_source` for a compact readiness/revision/last-good summary.
2. Edit literal JSX directly, or use `edit_project` with
   `operation=rewrite_graphics_source` and
   `params={source,expected_revision,edits:[{kind:"set",source:"index.tsx:title",props:{x:100,y:200}}]}`.
   This prepares source without mutating the graph.
3. `trigger_render` with `mode=graphics`, `expected_revision` and
   `graphics={source,duration_sec:3,fps:30}` queues a durable job. Poll
   `get_render_job`, or use `cancel_render_job`. Default results omit source,
   element arrays and verbose diagnostics.
4. After reviewing the successful preview, use `edit_project` with
   `operation=commit_graphics`, `params={job_id,expected_revision,clip_id:"title",track_id:"graphics",position_sec:0}`.
   New clips use that placement; updates keep their existing placement. The
   current revision must match the revision at which the preview was queued.

The HTTP studio uses the same Python adapters and durable service:
`GET /api/projects/{id}/graphics`, `POST .../graphics/source`, ordinary
`POST .../render`, `POST .../graphics/commit`, and job-specific
`.../graphics/{job_id}/poster` / `preview`. Stale source/commit writes return 409.

## Supported vocabulary and output

- One `stage`, one even-sized `scene` (16..1920 pixels per dimension).
- `rect`, `text`, `image`, `group`, `sequence`, solid paints, position, size,
  scale, rotation, opacity, corner radius and explicit source/timeline times.
  Groups derive bounds from their children and accept transform/opacity/timing
  properties; paint a child rect instead of setting a group fill or size.
  Every element needs a unique stable ASCII ID. Times are numeric seconds.
- Text uses `fontFamily="OpenEdit Sans"`; the font is bundled and no network
  font loading is allowed. Put plain literal text inside the text element.
- Rectangular `clipPath` masks; fade/grow/shrink/slide/spin presets; numeric
  x/y/size/rotation/scale/opacity and color keyframes with supported easing.
- Sequence children require explicit start/end timing. Their transitions use a literal
  `transition={{type:"dissolve",duration:0.4}}`; slide-from-left/right and
  fade-to-black/white are also mapped. Transition duration is at most 5 seconds.
- Images use SHA-256 `asset://` references from this project's CAS. Unknown,
  missing, corrupt or oversized assets fail before publication. Browser
  requests are intercepted by the host; external network requests are blocked.

Imports, arbitrary JavaScript, calls, spreads, loops, HTML, shaders, 3D,
generated assets, tracked mask sequences and audio/video elements inside the
graphics document are rejected. Put sound and footage on ordinary media
tracks. Graphics outputs are explicitly silent.

The pinned image encoder steps actual Chromium canvas frames. FFmpeg encodes
lossless RGBA QTRLE MOV for CAS and alpha VP9 WebM for browser review. The
complete MOV is probed and fully decoded before publication; dimensions,
duration, alpha and absence of audio are checked. A second revision check
protects the graph commit. Failed or cancelled jobs never append visual ops.

Limits: 512 KiB source, 500 elements, 20 nesting levels, 1,000 property edits,
60 seconds, 1..60 fps and at most 1,800 output frames. Duration rounds up to the
next output frame. Compilation and rendering have separate bounded worker
deadlines. Images are limited to 32 MiB each and 64 images / 64 MiB / 32 million
decoded source pixels in total. Keys include source, render settings, referenced content hashes,
vendored sources/font/lockfile, browser registry or override version, and
FFmpeg version. CAS bytes are rehashed before a cached result is reused.

## Source-time and audio parity

Media JSX supports constant `playbackRate` from 0.125 to 8. Before committing,
the adapter bakes the requested original source range into lossless FFV1/PCM
CAS media with normalized timestamps. NUT preserves audio sample timestamps;
audio-only outputs use WAV. Audio is resampled to 48 kHz and atempo preserves
pitch. Constant graph gain remains a separate operation.

Versioned provenance retains the original hash/range/rate. Fresh source views
project a baked clip and subsequent trims back into original source time.
Unchanged documents stay graph no-ops. Changed retiming is capped at 20 clips
per batch, with 60-second/1,800-frame output limits and decode/duration/audio QC.

`edit_project operation=retime_asset` can also prepare explicit
`segments=[{source_in,source_out,rate}, ...]` (1..32) and an output `fps`.
Segments are piecewise constant source-time intervals, including cuts or
repeated intervals. It returns a CAS asset without changing the graph; place
that asset through normal clip operations. Interpolated legacy speed ramps are
preserved as legacy operations and are not silently reinterpreted.

## Upgrade and validation

Graph schema 6 adds revision-owned source views; existing operations and IDs
are retained. The render-job table migrates its mode constraint while keeping
existing records. Keep the entire `.open_edit` directory when moving/backing
up a project: CAS, graphics/timing provenance and the SQLite graph belong
together. Runtime/dependency changes invalidate graphics keys automatically.
No integration is activated merely by upgrading Python.

See [execution evidence](DIFFUSION_EXECUTION_VALIDATION.md) for golden fixtures,
platform lifecycle checks, browser screenshots, compatibility checks and
`python tools/benchmark_diffusion.py --render` for reproducible measurements.
