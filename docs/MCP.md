# Open Edit as a local MCP server

Open Edit can run as a **local [MCP](https://modelcontextprotocol.io/) plugin**.
An external agent host (Cursor, Claude Code, MCP Inspector, …) owns the LLM
loop; Open Edit only executes editing and render tools against a pinned
project directory.

No cloud hosting is required. The MCP process is spawned over **stdio** on
your machine.

## Install

### Linux / macOS

From the repo root (use your project venv):

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[mcp]"
```

That installs the `mcp` SDK and the `open-edit-mcp` console script.

### Windows (native)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[mcp]"
```

Optional extras: `.[mcp,serve]` for the review UI, `.[mcp,whisper]` for local
transcription.

On Windows the Linux bwrap/Rust sandbox is **not** used. `run_script` defaults
to `OPEN_EDIT_SANDBOX_BACKEND=dev` (unsandboxed in the MCP process; the host
harness owns isolation). Moviepy `generate_visual_for_segment` is unsupported
(`render_sandbox_unsupported_on_windows`). Core IR edit, ingest, Remotion, and
`trigger_render` work when the PATH tools below are installed.

#### Windows PATH dependencies

| Tool | Needed for |
|---|---|
| Python 3.11+ | MCP server |
| ffmpeg / ffprobe | probe, overlays, Remotion burn-in |
| melt (MLT) | proxy/final timeline render (edit/query still work without it) |
| Node.js | Remotion compositions (`OPEN_EDIT_NODE_BIN` → `node.exe`) |

Safe render default on Windows: `OPEN_EDIT_RENDER_BACKEND=cpu` (already the
unset default). Set `gpu` to try NVENC/QSV.

#### Windows smoke checklist

1. `open-edit-mcp --project C:\path\to\project` starts; tools list includes the four pillars.
2. `query_project` / `edit_project` ingest + silence cut.
3. `run_script` minimal `ir.add_clip(...)` commits ops.
4. `trigger_render` proxy with melt+ffmpeg on PATH.
5. `generate_visual` returns unsupported (expected).

## Initialize a project

The MCP server requires an existing Open Edit project (a folder with
`.open_edit/`):

```bash
open_edit init /absolute/path/to/project
```

On Windows:

```powershell
open_edit init C:\Users\you\OpenEditProjects\my-talk
```

## Run standalone (debug)

```bash
open-edit-mcp --project /absolute/path/to/project
# or
open_edit mcp --project /absolute/path/to/project
# or
OPEN_EDIT_PROJECT=/absolute/path/to/project open-edit-mcp
```

Windows:

```powershell
open-edit-mcp --project C:\Users\you\OpenEditProjects\my-talk
# or
$env:OPEN_EDIT_PROJECT = "C:\Users\you\OpenEditProjects\my-talk"
open-edit-mcp
```

The process speaks MCP JSON-RPC on stdin/stdout. Do not type into it by
hand — point an MCP client at it.

## Cursor config

Add to `~/.cursor/mcp.json` or the project `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "open-edit": {
      "command": "open-edit-mcp",
      "args": ["--project", "/absolute/path/to/project"]
    }
  }
}
```

If `open-edit-mcp` is not on `PATH`, use the venv binary:

**Linux / macOS**

```json
{
  "mcpServers": {
    "open-edit": {
      "command": "/absolute/path/to/OpenEdit/.venv/bin/open-edit-mcp",
      "args": ["--project", "/absolute/path/to/project"]
    }
  }
}
```

**Windows**

```json
{
  "mcpServers": {
    "open-edit": {
      "command": "C:\\OpenEdit\\.venv\\Scripts\\open-edit-mcp.exe",
      "args": ["--project", "C:\\Users\\you\\OpenEditProjects\\my-talk"],
      "env": {
        "OPEN_EDIT_RENDER_BACKEND": "cpu"
      }
    }
  }
}
```

Restart Cursor (or reload MCP servers) after editing the config.

## Tools exposed

| Tool | Role |
|---|---|
| `query_project` | Read-only project queries |
| `edit_project` | Mutations + generate (incl. Remotion, `ingest_local`) |
| `run_script` | Free-form Python (bwrap sandbox on Linux; `dev` on Windows) |
| `trigger_render` | Enqueue + wait for proxy/final/overlay/preview-chunks |
| `get_render_job` | Poll a durable render job by `job_id` |
| `cancel_render_job` | Cancel a queued/running job |

### Local media ingest

```json
{
  "operation": "ingest_local",
  "params": {
    "paths": ["/absolute/path/to/clip.mp4"],
    "transcribe": true
  }
}
```

Paths must be absolute and may come from any readable local folder. Symlinks
are resolved before the file is copied into the project CAS.

### Arabic transcription

```bash
export OPEN_EDIT_WHISPER_LANGUAGE=ar
export OPEN_EDIT_WHISPER_MODEL=small   # recommended for Arabic
```

`project_path` is **not** a tool argument. It is fixed when the MCP process
starts (`--project` / `OPEN_EDIT_PROJECT`).

Renders go through `RenderJobService`: native HyperFrames graphics materialize
on the host worker → melt the full timeline → **ffmpeg composite/encode**
(proxy/final). Legacy Remotion graphs remain compatibility inputs during
migration. `mode=proxy`
defaults to the `review-artifact` emission profile and is a complete-timeline
**whole-file review artifact** using the `fast_proxy` 640×360 profile; it is
not an interactive timeline preview. The M3 **timeline preview chunks** mode is
a separate range-cache product described below; a **source proxy** is a separate
low-resolution per-asset CAS sibling used only by the `proxy-edit` and
`preview-chunk` emission profiles. `mode=preview-chunks` is that range-cache
product; it does not redefine
`mode=proxy`.

The emission policy is explicit: `final` and `review-artifact` always read
canonical original sources, while `proxy-edit` and `preview-chunk` may use a
ready source proxy with canonical fallback. Therefore `mode=final` always
uses originals even when `proxy_hash` is ready. The host-side
`generate-asset-proxy` job reports `proxy_hash`, `proxy_profile`, and
`proxy_status` through asset/project state; it does not expose a guessed proxy
filesystem path. Free-form `run_script` remains sandboxed IR editing and never
renders preview media or writes preview cache files.

## Review UI (recommended with MCP)

Run the **review studio** alongside MCP so you can preview proxy renders,
scrub the timeline, revert bad edits, and leave time-scoped notes for the
harness — without any built-in LLM providers in Open Edit.

```bash
# Terminal 1 — MCP (Cursor spawns this automatically from mcp.json)
open-edit-mcp --project /absolute/path/to/project

# Terminal 2 — review UI
open_edit serve --review-only --port 8000
```

Open `http://127.0.0.1:8000`, select the same project, then:

1. **Render review artifact** (640×360, fast) — review the full cut in the center player.
2. Scrub the timeline, **Copy time** (`[MM:SS.ms]`) for Cursor chat, or
   **Note here** to write a pending note the agent reads via
   `query_project` → `get_pending_notes`.
3. Revert unwanted ops in the **Edit graph** panel (or click orange markers
   on the timeline).
4. **Render final** (1080p) when satisfied.

Optional: auto-enqueue proxy after MCP graph changes:

```bash
export OPEN_EDIT_AUTO_PROXY=1
open_edit serve --review-only
```

### Two-stage render workflow (MCP or UI)

| Stage | Mode | Resolution | Purpose |
|---|---|---|---|
| Review artifact | `proxy` | 640x360 fast_proxy | Full-timeline review, iterate with harness |
| Delivery | `final` | 1080p30 | Full-quality export |

`mode=proxy` is one complete MP4 review artifact, not interactive scrub and
not a per-asset source proxy. A future preview-chunk worker may use ready
source proxies for dirty-range chunks; that product is separate from the
review artifact.

From MCP: `trigger_render` with `"mode": "proxy"` then `"mode": "final"`.

The UI warns before final render if the latest proxy does not match the
current edit graph hash.

### Range preview chunks (MCP)

Use the existing `trigger_render` tool for the manifest-backed
`preview-chunks` job. It is a background range cache, not a second whole-file
render product:

```json
{
  "mode": "preview-chunks",
  "ranges": [{"start_sec": 12.0, "end_sec": 20.0}],
  "media": "both",
  "priority": "interactive",
  "wait": false
}
```

`ranges` is optional and uses project seconds. Omitted ranges request all dirty
chunks in manifest order. `media` is `video`, `audio`, or `both`; video and
audio are independent cache planes, with a cheap muxed `playback` artifact.
`priority` is `interactive` or `background`; interactive requests prioritize a
playhead window, while background requests may cover all dirty ranges. Chunk
geometry, codecs, and cache policy remain server/profile policy.

The MCP/REST enqueue path is **enabled by default**. Set
`OPEN_EDIT_PREVIEW_CHUNKS=0` to disable preview generation without affecting
`proxy` or `final`. With
`wait=false` (the default), save the returned durable `job_id` and poll:

```json
{"job_id": "<job-id>"}
```

`get_render_job` returns the terminal manifest-oriented `result` and progress
counts; it does not turn `manifest.json` into a whole-file MP4. Read the
manifest's red/yellow/green status and the independent `video` and `audio`
plane states. A yellow chunk keeps an exact **same-range** prior artifact as a
playable fallback while the current range bakes. A red chunk has no usable
current or same-range artifact, so clients may use the newest whole-file proxy
only as an explicitly stale `proxy_fallback`, never as a neighboring range.

Project-scoped routes expose only indexed artifact IDs and browser-safe URLs:

```text
GET    /api/projects/{project_id}/preview-chunks
GET    /api/projects/{project_id}/preview-chunks/files/{artifact_id}
DELETE /api/projects/{project_id}/preview-chunks
```

The manifest route returns `manifest`, `active_job`, and `proxy_fallback`.
The file route validates the artifact index, stays inside the project preview
cache, and supports `Accept-Ranges: bytes`. The delete route wipes preview
artifacts only; it does not cancel or remove proxy/final jobs, the Edit Graph,
or whole-file artifacts.

M3 playback uses sequential self-contained MP4 chunks by default. MSE/fMP4 is
an optional future strategy, not an M3 correctness requirement. A live MLT
SDL/OpenGL/shared-memory consumer is out of scope until M4.

### QC and cache controls

Inspect `qc_report.policy` and `qc_report.complete` in the
`trigger_render`/`get_render_job` result. A warm proxy deliverable-cache hit
may use `policy=skip` or `policy=light`; `passed=true` does not make skipped
checks complete evidence. Final and overlay QC remain `full`. A duration-aware
blackdetect timeout is incomplete diagnostic evidence, not permission to ship
the final export blindly.

Operator controls are configured through:

- `OPEN_EDIT_PROXY_QC_MODE` (`light` by default) for cold proxy artifacts.
- `OPEN_EDIT_PROXY_WARM_QC_MODE` (`skip` by default) for warm proxy hits.
- `OPEN_EDIT_PROXY_QC_POLICY` (`always`, `skip_on_hit`, or `never`) as the
  M1 compatibility override for proxy QC.
- `OPEN_EDIT_AUTO_PROXY=1` keeps the existing auto-proxy behavior; it is
  independent from `OPEN_EDIT_AUTO_PREVIEW=1`, which permits automatic
  preview-chunk requests after graph changes.
- `OPEN_EDIT_PREVIEW_CACHE_MAX_BYTES` (512 MiB by default) caps preview
  artifacts, and `OPEN_EDIT_PREVIEW_CACHE_MAX_AGE_SEC` (7 days by default)
  controls preview artifact TTL.
- `OPEN_EDIT_CACHE_MIN_FREE_BYTES` reserves free space for preview writes.
- `OPEN_EDIT_PREVIEW_CHUNKS=0` disables MCP/REST preview enqueue (default on);
  `OPEN_EDIT_AUTO_PREVIEW` does not bypass that rollout gate.
- `OPEN_EDIT_FINAL_QC_BUDGET_SEC` and
  `OPEN_EDIT_QC_BLACKDETECT_MAX_SEC` (900 seconds by default).
- `OPEN_EDIT_RENDER_CACHE_MAX_BYTES`,
  `OPEN_EDIT_REMOTION_CACHE_MAX_BYTES`, and
  `OPEN_EDIT_SOURCE_PROXY_MAX_BYTES` for derived-media byte budgets.
- `OPEN_EDIT_CACHE_MAX_AGE_SEC` and `OPEN_EDIT_CACHE_MIN_FREE_BYTES` for
  age and disk-pressure cleanup.

Cache eviction protects canonical source CAS and sidecars, active jobs, and
newest deliverables. It may remove regenerable source proxies, Remotion
materialize outputs, render-cache entries, and orphaned temporary files.

### Remotion / Node

Prefer Node 24 for Remotion CLI:

```json
{
  "mcpServers": {
    "open-edit": {
      "command": "/path/to/OpenEdit/.venv/bin/open-edit-mcp",
      "args": ["--project", "/absolute/path/to/project"],
      "env": {
        "OPEN_EDIT_NODE_BIN": "/path/to/node24/bin/node",
        "OPEN_EDIT_WHISPER_LANGUAGE": "ar",
        "OPEN_EDIT_WHISPER_MODEL": "small"
      }
    }
  }
}
```

## Agent skills (all harnesses)

Canonical playbooks live in the repo **`skills/`** folder — not Cursor-only:

| File | Role |
|---|---|
| [`skills/open-edit-mcp.md`](../skills/open-edit-mcp.md) | **Start here** — tools, when to use, recipes |
| [`skills/open-edit-mcp-reference.md`](../skills/open-edit-mcp-reference.md) | IR / `run_script` |
| [`skills/README.md`](../skills/README.md) | Full skill index |

Also shipped inside the Python package as `open_edit/harness_skills/` (for
installed wheels). Override search path with `OPEN_EDIT_SKILLS_DIR`.

### How hosts load them

1. **Filesystem** — read `skills/open-edit-mcp.md`
2. **MCP initialize `instructions`** — playbook text is sent to the client
3. **MCP resources** — `open-edit://skills/open-edit-mcp`, `…/open-edit-mcp-reference`, …
4. **MCP prompts** — `open-edit-playbook`, `open-edit-reference`
5. **Python** — `from open_edit.mcp.skills import load_skill`

Cursor also has a thin pointer under `.cursor/skills/open-edit-mcp/` that
redirects to the same project files.

Longer planning docs:

- [`skills/tool_surface.md`](../skills/tool_surface.md)
- [`skills/edit-planning.md`](../skills/edit-planning.md)
- [`skills/remotion_motion.md`](../skills/remotion_motion.md)

## Security notes

- Tools are project-scoped to the pinned project; local ingestion copies any
  readable absolute media path into the project CAS.
- `run_script` uses the bwrap sandbox on Linux by default. On Windows it
  defaults to `OPEN_EDIT_SANDBOX_BACKEND=dev` (no jail — rely on the MCP host).
  Explicit `OPEN_EDIT_SANDBOX_BACKEND=bwrap` is rejected on Windows.
- Moviepy `generate_visual_for_segment` requires the Linux render-sandbox
  binary and is unsupported on Windows.
- Prefer an absolute project path in MCP config; do not point at untrusted trees.

## License

MCP itself is free. Remotion licensing (if you use Remotion compositions) is
separate — see [`REMOTION_LICENSE.md`](REMOTION_LICENSE.md).
