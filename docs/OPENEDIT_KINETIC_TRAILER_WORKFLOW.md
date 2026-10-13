# OpenEdit kinetic trailer: authoring and verification

The second version is a ten-second 1920×1080, 60 fps product trailer. Its five
beats are "Your ideas", "Just say it", "Let it flow", "Ready to share" and the
OpenEdit logo. It uses original geometric artwork and deterministic synthesized
stereo audio. Film cards fly into place, footage has moving perspective marks,
the selected region receives a prompt, the timeline snaps together, and burst
particles settle around the closing logo. Music and effects remain separate
audio clips; the effects include stereo sweeps, UI ticks, low impacts and a
three-note export chime.

## Actual OpenEdit workflow

1. Generated editable JSX artwork and two original audio stems, without rendering
   a video externally. The generator is `examples/openedit-explainer/author_trailer.py`.
2. Imported the stems through the real stdio MCP `edit_project ingest_local` tool.
   Queried assets/editing context and atomically created the graphics document
   and audio clips through `apply_studio_changes`.
3. Opened the project in OpenEdit's browser Graphics view. Scrubbed six scene
   times, inspected its actual canvas, and revised the graphics through MCP.
4. Exported three iterations through the actual Export dialog using CPU H.264,
   high quality, 1080p/60 fps and stereo 48 kHz AAC. All exports reported
   "Export verified and saved" and had no browser JavaScript errors.
5. Probed and fully decoded the final MP4; inspected frames from the exported
   file rather than relying only on the canvas. Tested source regeneration,
   recreation of a new project and relocation of the editable archive.

The illustrated prompt inside the trailer is part of its motion graphics. The
authoring used actual OpenEdit MCP calls and UI controls; it does not demonstrate
a live OpenCode model independently deciding an edit.

## Friction found and addressed

| Observation | Change and evidence |
|---|---|
| The 500-element cap counted animation tracks and every keyframe. A composition with fewer than 500 visual layers failed. | Kept the 500-visual-layer bound and added a separate 4,096-total-node bound, retaining source/time/depth limits. Tests accept dense animation and reject both excessive layers and nodes. The final trailer has 2,938 nodes and remains below both bounds. |
| Completed graphics metadata truncated animation/layers after node 500. | Preserve the complete bounded element list. Verified the final saved cache contains all 2,938 nodes, with working live canvas editing. |
| Exports captured before an automatic preview finished repeated its full graphics render. | Before rendering, import completed cache records that exactly match the immutable captured source, duration and fps. A real-media regression test forbids new frame capture and confirms later source edits and unrelated cache records cannot change the frozen export. |
| The play character rendered as an orange color emoji. | Replaced it with literal geometry. A second pass overlapped the narrow bars to remove visible antialias seams. Inspected the final exported frame. |
| Numeric font weights are required, while the first source used `"bold"`. | Corrected the original authoring source to weight 700. This was an authoring mistake; validation preserved the project. |
| Canvas initialization takes longer than merely loading its source text. | Waited for the canvas to mount before measuring seeks or taking review images. First-run initialization is excluded from the seek timings. |

## Observed measurements and limits

Initial UI export: 125.952 seconds. The richer animation refinement took
136.979 seconds before the late-preview-cache fix. The final comparable edit
took 82.695 seconds after it, including waiting for automatic preview work.
These are observations on this CPU cloud machine, not isolated cross-hardware
benchmarks. Automatic preview work still serializes with export on a project;
the fix avoids duplicate graphics capture after that preview completes.

The final fresh-browser canvas review measured six two-animation-frame updates
at 29.2–41.9 ms, with no browser errors. This measures interactive canvas updates,
not cold video decode or a universal playback guarantee. Source is approximately
252 KiB of literal JSX; compact project queries need not return that source.

Final video: exactly 600 frames and 10.000 seconds; stereo AAC 48 kHz, 10.005
seconds including encoder padding. Complete decode succeeds. Decoded audio peak
is 0.8473, with zero clipped samples; measured loudness is -17.63 LUFS and true
peak -1.23 dBTP. The editable ZIP omits generated caches and regenerates graphics
with the current installed OpenEdit runtime.

The actual downloadable ZIP was extracted to a different directory and opened
in a fresh server/browser session. Revision 5, all three timeline tracks, the
ten-second duration and full graphics source survived; all six canvas scenes
rendered with no browser errors. The full regression run passed 1,797 tests,
with 11 browser-marked tests deselected and three existing Pillow deprecation
warnings. The actual browser authoring/export/archive workflows above were run
separately. Lint, whitespace checks and the wheel build passed.

See `OPENEDIT_KINETIC_TRAILER_METRICS.json` for machine-readable final evidence.
