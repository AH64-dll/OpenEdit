# Task 8 — Remotion frame-pull protocol

## Status

Implemented and committed as `bc66c99` (`feat: add host remotion frame pull protocol`).

## Delivered

- Added `FrameRequest`, validated PNG response framing, bounded JSON/payload limits,
  timeout/EOF/nonzero-exit cleanup, and the materialize-default engine selector.
- Added a host-only Node stdin/stdout server using the verified
  `bundle` → `selectComposition` → `renderStill` APIs. It bundles once per entry
  point, caches composition metadata, enforces composition frame bounds, returns
  PNG bytes without an output path, and exits when stdin closes.
- Added scaffold/root package pins for `@remotion/bundler` and
  `@remotion/renderer` at `4.0.278`; regenerated `package-lock.json`.
- Kept browser reuse disabled intentionally. The pinned declarations confirm
  `openBrowser(browser, options)` and `renderStill({puppeteerInstance})`, but
  the server records the per-render lifecycle in response diagnostics until
  lifecycle/memory behavior is measured.

## Verification

- `.venv/bin/python -m pytest -q tests/test_remotion_frame_engine.py tests/test_remotion_scaffold.py tests/test_remotion_renderer.py tests/test_remotion_ir_materialize.py`
  — 28 passed.
- `node --check open_edit/render/remotion_frame_server.mjs` — passed.
- `npm ls @remotion/bundler @remotion/renderer remotion` — all resolve to
  `4.0.278`.
- Temporary scaffold API probe with system Chrome verified a bundle URL,
  `TitleCard` selection, `renderStill()` PNG buffer, and `renderFrames()` with
  `frameRange: [0, 0]` writing one PNG (`element-0.png`).
- Real frame-server smoke test returned a 640×360 PNG (`5999` bytes) with
  `OPEN_EDIT_REMOTION_CHROME_BIN=/usr/bin/google-chrome-stable`.

## Concerns

- `OPEN_EDIT_REMOTION_FRAME_ENGINE=pull` remains protocol/integration-test-only;
  normal renders remain materialize-default and receive
  `remotion_frame_pull_unavailable` unless explicitly allowed.
- Hosts without a configured/downloadable Remotion browser will return a bounded
  protocol error; no composition media artifact is created on that path.
