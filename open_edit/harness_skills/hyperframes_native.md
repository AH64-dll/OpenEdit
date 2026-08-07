---
name: hyperframes_native
description: Route Open Edit motion graphics and render decisions through native HyperFrames HTML/CSS/JS contracts.
---

# HyperFrames native guide

Use this guide for new motion graphics, preview chunks, and final renders.

## Route

1. Read `skills/open-edit-mcp.md`.
2. Query project state with `query_project`.
3. Use `edit_project` for timeline edits.
4. Use native HyperFrames HTML composition operations for new graphics.
5. Use `trigger_render` with `preview-chunks` for dirty-range review.
6. Use `trigger_render` with `proxy` for full-cut review artifact.
7. Use `trigger_render` with `final` only after review approval.
8. Poll non-blocking jobs with `get_render_job`.

## Native composition contract

HyperFrames projects use HTML/CSS/JavaScript, not React or JSX. A composition root declares:

- `data-composition-id`
- `data-start`
- `data-duration`
- `data-width`
- `data-height`
- `data-fps`

Timed elements use `class="clip"`, stable `id`, `data-start`, `data-duration`, and `data-track-index`. Register seekable animation in `window.__timelines`, or add `data-no-timeline` for static content. Run HyperFrames lint before render.

Use seek-safe CSS, WAAPI, GSAP, or another supported adapter. Avoid wall-clock-only animation. Keep local media paths inside project-managed composition assets.

## Remotion migration

Existing `add_remotion_composition` graph operations are migration inputs. Do not create new Remotion compositions. Inspect legacy source only when porting it to HTML. Preserve composition UID, timing, track, props, and alpha intent in the migration record. Do not delete legacy operations until converted output passes frame-parity tests.

## Render architecture

- HyperFrames owns HTML/CSS/JS graphics capture and its MP4/MOV/PNG output.
- MLT remains the base timeline/audio compositor during migration.
- FFmpeg remains the final mux/composite boundary until HyperFrames A/V parity is proven.
- GPU encoding is host-worker only. Never place HyperFrames, Chrome, FFmpeg, or GPU access in `run_script` sandbox.
- Preview and final use separate profiles and caches. Preview invalidates dirty ranges; final uses canonical original assets.

## Token rule

Do not search the repository for HyperFrames APIs. Load this guide, then only the architecture map and the files named by the active operation.
