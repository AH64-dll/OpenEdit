# OpenEdit in ten seconds — actual workflow and friction

Created on 2026-10-13 in the OpenEdit checkout. This is an original 1920×1080,
30 fps, ten-second motion graphic with a synthesized stereo score. It introduces
OpenEdit through selecting a moment, directing an edit, arranging a story and
exporting it. The source stays editable, with stable IDs and animation tracks.

## What actually used OpenEdit

- Initialized a real project and connected to `open_edit.mcp.server` over stdio.
- Imported `score.wav` through `edit_project ingest_local`.
- Created the animation document and audio clip together with
  `edit_project apply_studio_changes`. OpenEdit compiled the source and committed
  the graph at revision 2; it did not receive a separately rendered animation.
- Scrubbed four scenes on OpenEdit's interactive graphics canvas, then inspected
  their corresponding frames from the exported MP4.
- Adjusted the score through `edit_project set_audio_gain` (+9.5 dB), producing
  revision 3. No animation source round trip was needed for this refinement.
- Exported through the application's browser export dialog: H.264, high quality,
  1080p/30 fps, CPU encoding, stereo 48 kHz AAC. OpenEdit captured, rendered,
  verified and saved the exports. FFmpeg was used afterward only for inspection.
- Reopened the project in a fresh server/browser session. The graphics source,
  ten-second timeline, audio track and revision 3 survived. Four live canvas
  seeks took 19.8–25.0 ms through two animation frames, with no browser errors.
  These are canvas update measurements, not uncached video-seeking measurements.

## Problems found and changes made

| Observation | Resolution and verification |
|---|---|
| Built-in OpenCode was chat-only and was not connected to the project's MCP server. Native tool activity was dropped. | OpenCode now gets a project-specific MCP connection and an editing agent. Native calls/results appear in the UI/history without being executed twice. Installed OpenCode 1.19.0 reports the server connected. A scripted CLI subprocess made a real MCP mutation in an integration test; the graph advanced exactly once. |
| Generic coding activity could distract a CLI editor from its actual task. | The OpenCode editing agent uses OpenEdit's six composable tools. Generic file/shell tools are denied for this app-owned agent; `run_script` still provides the application's flexible Python editing interface. This does not change a separately launched external agent's configuration. |
| `describe apply_studio_changes` returned no nested data example and exposed internal Python arguments. | Added document/caption/annotation examples and removed `project_path` and private flags from exposed signatures. Added a regression test. Graphics text/property edits now have a concise example too. |
| Duplicate keyframe errors did not identify the offending animation. | Errors now identify track, frame and time. Verified with a real compiler test. |
| An audio-only refinement still took 37.4 seconds to export: frozen export snapshots lost reusable graphics. | Snapshots retain completed graphics records and immutable derived media. Verified exports return those records to the project before snapshot cleanup. Reuse is limited to graphics referenced by the captured timeline. Derived files stay out of the import library. A real-media test deletes the live cache and prohibits frame rendering, then successfully reuses the next snapshot's cache. |
| A CLI could emit text, then fail, and still end like a successful turn. | Nonzero exits and error events remain failures. CLI shutdown gives it time to reap its MCP subprocess. Timeout/error regression tests pass. |

Export timings for this project were 52.4 seconds initially, 37.4 seconds after
raising audio gain before the cache fix, and 14.3 / 16.3 seconds after the cache
fix. These are observed UI-to-verified-file times on this CPU machine, with
regression tests also running. They are not an isolated hardware benchmark or a
claim that changed graphics never need to render again.

## My authoring mistakes, separate from application defects

I initially used `path` instead of `paths: [absolute_path]` for import, assumed an
asset-list row used `asset_hash` rather than `hash`, and generated duplicate
zero-time keyframes. I corrected each. Nineteen MCP call records are retained in
`mcp-calls`; two returned structured errors. The asset-field mistake happened in
my authoring script before an edit call. One additional repeated audio-help query
was overwritten in the retained record. These counts are not a model benchmark.

## Remaining friction and limits

- Chromium discovery needed `OPEN_EDIT_CHROMIUM=/usr/bin/chromium` in this cloud
  container. Headless capture also required its existing no-sandbox setting.
- Automatic timeline previews can do background composition work while the
  graphics canvas is being reviewed. There is no simple pause control exposed
  for that work. Interactive canvas scrubbing itself needs no explicit export.
- A large composition's flat layer list exposes many decorative elements. Direct
  canvas selection works, but the layer list could use grouping/filtering.
- First-time graphics materialization still captures the composition's frames.
  Caching speeds reuse; it does not provide partial scene recompilation.
- A live OpenCode request using `opencode/ling-3.1-flash-free` failed after 3.8 s
  with `Forbidden: Domain forbidden`, before any editing calls. A fallback CLI
  also hit the cloud proxy's HTTP 403 policy. No policy bypass was attempted.
  The local MCP connection and scripted transport are verified; live model
  behavior, semantic accuracy and billed token savings are **not verified**.
  The animation was authored through OpenEdit's MCP tools by the current agent,
  not by the blocked built-in model. No extra provider was shipped for the
  unsuccessful fallback experiment.

## Output checks

The final MP4 has exactly 300 video frames, 1920×1080, 30/1 fps and ten seconds of
video. Stereo AAC starts at zero and lasts 10.005 seconds (5 ms of codec padding).
A full decode reports no errors. The decoded score peaks at 0.602, with zero
clipped samples. Exported and reopened frames were reviewed at 0.9, 3.8, 6.6 and
8.9 seconds. There is no voiceover. Source, project data, original audio and this
log are included in the editable-project archive.

Final validation: 1,788 non-browser tests passed; 11 browser-marked tests were
deselected. Lint and whitespace checks passed. This workflow also performed
actual browser exports and a browser reopen. Detailed measurements are in
`OPENEDIT_EXPLAINER_METRICS.json`.
