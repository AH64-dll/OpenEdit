# Operating Open Edit

Operator-facing configuration and render internals. Agent-facing guidance lives
in `skills/` (served over MCP); this page holds what an agent does not need on
every task.

## Runtime binaries

`open_edit doctor` (or MCP `query_project get_readiness`) reports each
capability, where every binary was found, and the exact fix. Binaries are
resolved in this order, and the CLI and MCP server prepend any directory found
off `PATH` so render workers and HyperFrames' `env node` shim inherit it:

| Binary | Order |
|---|---|
| Node.js ≥ 24 | `OPEN_EDIT_NODE_BIN` → `PATH` → nvm (`$NVM_DIR`) → fnm → asdf → volta → `<checkout>/.node` |
| melt (MLT) | `OPEN_EDIT_MELT` → `PATH` → `~/.local/share/OpenEdit/runtime/bin/melt` → Shotcut portable (`*/Shotcut.app/melt`) |
| Chromium (Diffusion graphics) | `OPEN_EDIT_CHROMIUM` → Playwright cache. A system Chrome is reported but must be set explicitly, because the browser is part of the graphics cache key. |
| HyperFrames browser | `HYPERFRAMES_BROWSER_PATH` → `~/.cache/hyperframes/chrome` → puppeteer cache (`hyperframes browser ensure` installs one) |

An explicit override that points nowhere is reported as missing; it never
silently falls back. melt is required for every render, including
graphics-only timelines: HyperFrames output is composited on the MLT timeline.

## Render products

- `mode=proxy`: one complete 640x360 review MP4 (`review-artifact` profile,
  canonical sources).
- `mode=final`: the delivery export; always canonical originals.
- `preview-chunks`: a range cache. Sequential self-contained MP4 chunks per
  plane (video, audio) plus a cheap `playback` mux. Chunk states are
  green/yellow/red; yellow plays the exact same-range prior artifact while it
  re-bakes. Disable with `OPEN_EDIT_PREVIEW_CHUNKS=0` (proxy/final unaffected).
- A **source proxy** is a low-resolution CAS sibling of one source asset
  (`proxy_hash`, `proxy_status`). Only the `proxy-edit` and `preview-chunk`
  emission profiles use it, falling back to the original while it is not ready.

Preview HTTP routes (review UI):

```text
GET    /api/projects/{project_id}/preview-chunks
GET    /api/projects/{project_id}/preview-chunks/files/{artifact_id}
DELETE /api/projects/{project_id}/preview-chunks
```

`encoder=gpu` (default) probes NVENC, AMF, QSV then falls back to libx264;
`diagnostics.profile.encoder_vcodec` records the codec actually used. Force
CPU with `OPEN_EDIT_RENDER_BACKEND=cpu`.

## QC policy

Every successful render runs the deterministic QC gate and attaches
`qc_report {policy, complete, passed, checks}`. `complete=false` means checks
were skipped (warm cache) or timed out and is not evidence of passing.

| Variable | Default | Meaning |
|---|---|---|
| `OPEN_EDIT_PROXY_QC_MODE` | `light` | cold `mode=proxy` QC |
| `OPEN_EDIT_PROXY_WARM_QC_MODE` | `skip` | warm proxy cache hit (`light` available) |
| `OPEN_EDIT_PROXY_QC_POLICY` | unset | M1 override: `always`, `skip_on_hit`, `never` |
| `OPEN_EDIT_FINAL_QC_BUDGET_SEC` | 900 | total final/overlay QC budget |
| `OPEN_EDIT_QC_BLACKDETECT_MAX_SEC` | 900 | black-frame detection cap |

## Cache budgets

Canonical sources, active jobs and the newest deliverables are protected;
regenerable proxies, materialized graphics and render-cache entries are
evicted under budget or disk pressure. Invalid values fall back to defaults.

| Variable | Default |
|---|---|
| `OPEN_EDIT_RENDER_CACHE_MAX_BYTES` | 1 GiB |
| `OPEN_EDIT_REMOTION_CACHE_MAX_BYTES` | 512 MiB |
| `OPEN_EDIT_SOURCE_PROXY_MAX_BYTES` | 1 GiB |
| `OPEN_EDIT_PREVIEW_CACHE_MAX_BYTES` | 512 MiB |
| `OPEN_EDIT_PREVIEW_CACHE_MAX_AGE_SEC` | 7 days |
| `OPEN_EDIT_CACHE_MAX_AGE_SEC` | 86400 |
| `OPEN_EDIT_CACHE_MIN_FREE_BYTES` | 512 MiB |

## Other variables

| Variable | Purpose |
|---|---|
| `OPEN_EDIT_WHISPER_LANGUAGE` / `OPEN_EDIT_WHISPER_MODEL` | transcription language / model |
| `OPEN_EDIT_AUTO_PROXY` / `OPEN_EDIT_AUTO_PREVIEW` | serve: render after graph changes |
| `OPEN_EDIT_HYPERFRAMES_BIN` | use a specific HyperFrames CLI |
| `OPEN_EDIT_HYPERFRAMES_TIMEOUT_SECONDS` | overlay render timeout (3600) |
| `OPEN_EDIT_SKILLS_DIR` | override the agent skills directory |

## Processes

| Process | Role |
|---|---|
| `open-edit-mcp --project P` | agent tools over stdio MCP |
| `open_edit serve` | Review Studio: preview, scrub, notes, revert (review-only by default) |
