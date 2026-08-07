# M3 Task 1 — Preview frame-engine handoff

## Result

- Added `PreviewVideoRequest` and `PreviewVideoRenderer` in
  `open_edit/render/frame_engine.py`.
- Added the contract test covering two composition UIDs plus wider context
  and narrower core frame ranges.
- No Remotion implementation, preview manifest, or chunk geometry was changed.

## Verification

- Focused test first failed because the handoff module was absent.
- Focused contract test passed after adding the seam.
- Selected contract, Remotion renderer, and orchestrator tests passed.
- Owned-file lints reported no errors.
