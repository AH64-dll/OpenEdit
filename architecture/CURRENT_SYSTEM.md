# Current System Architecture (2026-07-25)

## Product Path

**Primary product surface:** the Python FastAPI server/UI under `open_edit/`.

**Legacy path:** the Go/MLT pipeline under `cmd/`, `internal/`, `run.sh`, and `edit.sh`.
It remains available for compilation/rendering work and must be reached through a
deliberate adapter rather than treated as a second product.

**Startup commands:**

- Python server: `python -m open_edit serve` (or the desktop launcher)
- Go pipeline (legacy): `./run.sh <project-name>` or `./edit.sh <source>`

## Supported Runtime Boundary

```
Browser UI
   |
FastAPI / WebSocket gateway (`open_edit/serve`)
   |
Application services (projects, assets, edit graph, agent, render)
   |
Canonical IR + SQLite stores under `<project>/.open_edit/`
   |
Compiler/render backend (Python CLI / RenderService; Go/MLT via adapter)
```

## Stabilization Status (summary)

Implemented and covered by regression tests:

- Canonical provider registry with `agent_mode` and `context_strategy`
- JCode hidden until a real adapter exists
- Multi-file ingest (`files[]`) with unique inbox paths and size limits
- Transactional project creation via Python storage APIs
- Timeline summary derived from applied IR, not raw asset sum
- LLM config TOML preservation
- Provider-scoped API key resolution
- Pi cost delta from session file offset
- WebSocket auth/origin/rate limits for remote access
- Durable `RenderService` with SQLite jobs and restart orphan recovery
- Edit-graph revision / optimistic concurrency core
- Chat-only CLI adapters receive full conversation history each turn

Still open relative to `OpenEdit_Repair_Plan.md`:

- Full browser E2E (Playwright) golden workflow
- Complete Go/Python render contract parity
- Remaining render acceptance cases (real child cleanup under melt/ffmpeg,
  overlay path folded into RenderService)
- Broader observability / project-health repair tooling (Phase 9)
- CI release gates (Phase 10)

## Media Fixtures

Deterministic fixtures live under `testdata/`:

- `video_with_audio.mp4`
- `video_no_audio.mp4`
- `still_image.png`
- `invalid_file.mp4`

## Motion Graphics Backends

- **HyperFrames**: `AddHtmlOverlayOp` → late composite when `mode=overlay`
- **Remotion**: `AddRemotionCompositionOp` → materialize to CAS → melt talk → ffmpeg burn-in (proxy/final)
- **moviepy**: legacy `generate_visual_for_segment` template path

See `docs/REMOTION_LICENSE.md` and `docs/architecture/TARGET_SYSTEM.md`.
