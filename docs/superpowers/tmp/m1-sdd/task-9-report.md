# Task 9 — Gated Remotion same-pass frame feeder

## Status

Implemented on `feat/render-m0-m1-remotion-engine`.

Commit: `aaef288` (`feat: add gated remotion same-pass frame feeder`)

## Delivered

- Added `FrameOverlaySpec` and `FrameFeeder`; requests source frames monotonically
  and streams PNG bytes without creating Remotion media artifacts.
- Added deterministic `pipe:3+` image2pipe inputs while preserving the melt
  `f=rawvideo` command and existing file-overlay filter timing/alpha behavior.
- Added POSIX inherited-descriptor lifecycle management, backpressure, timeout,
  melt/ffmpeg failure cleanup, bounded feeder errors, and explicit fallback opt-in.
- Wired the proxy-first `OPEN_EDIT_REMOTION_FRAME_ENGINE=pull` gate, host/platform
  probe, final-export safety gate, and `remotion_frame_pull` diagnostics.

## Verification

- `.venv/bin/python -m pytest -q tests/test_remotion_frame_engine.py tests/test_render/test_pipe_builder.py tests/test_render/test_run_pipe.py tests/test_render/test_orchestrator.py tests/test_render/test_orchestrator_timeout.py tests/test_remotion_renderer.py tests/test_remotion_ir_materialize.py`
- `.venv/bin/python -m pytest -q tests/test_render`
- Real ffmpeg frame-pipe smoke test passed; Windows remains materialize-only until named pipes exist.
