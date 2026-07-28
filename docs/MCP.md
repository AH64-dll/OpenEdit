# Open Edit as a local MCP server

Open Edit can run as a **local [MCP](https://modelcontextprotocol.io/) plugin**.
An external agent host (Cursor, Claude Code, MCP Inspector, …) owns the LLM
loop; Open Edit only executes editing and render tools against a pinned
project directory.

No cloud hosting is required. The MCP process is spawned over **stdio** on
your machine.

## Install

### Linux / macOS

From the `open_edit/` package directory (use your project venv):

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[mcp]"
```

That installs the `mcp` SDK and the `open-edit-mcp` console script.

### Windows (native)

```powershell
cd open_edit
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
      "command": "/absolute/path/to/open_edit/.venv/bin/open-edit-mcp",
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
      "command": "C:\\absolute\\path\\to\\open_edit\\.venv\\Scripts\\open-edit-mcp.exe",
      "args": ["--project", "C:\\Users\\you\\OpenEditProjects\\my-talk"],
      "env": {
        "OPEN_EDIT_RENDER_BACKEND": "cpu",
        "OPEN_EDIT_INGEST_ALLOWLIST": "C:\\Users\\you\\Videos;C:\\Users\\you\\Music"
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
| `trigger_render` | Enqueue + wait for proxy/final/overlay |
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

Paths must be absolute and under the pinned project directory **or** under
`OPEN_EDIT_INGEST_ALLOWLIST` (`os.pathsep`-separated absolute roots: `:` on
POSIX, `;` on Windows), e.g.:

```bash
export OPEN_EDIT_INGEST_ALLOWLIST=/home/you/Videos:/home/you/Music
```

```powershell
$env:OPEN_EDIT_INGEST_ALLOWLIST = "C:\Users\you\Videos;C:\Users\you\Music"
```

### Arabic transcription

```bash
export OPEN_EDIT_WHISPER_LANGUAGE=ar
export OPEN_EDIT_WHISPER_MODEL=small   # recommended for Arabic
```

`project_path` is **not** a tool argument. It is fixed when the MCP process
starts (`--project` / `OPEN_EDIT_PROJECT`).

Renders go through `RenderService`: Remotion **materialize** → melt talk
timeline → **ffmpeg burn-in** of Remotion graphics (proxy/final).

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

1. **Render proxy** (720p, fast) — preview in the center player.
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
| Preview | `proxy` | 720p30 | Fast review, iterate with harness |
| Delivery | `final` | 1080p30 | Full-quality export |

From MCP: `trigger_render` with `"mode": "proxy"` then `"mode": "final"`.

The UI warns before final render if the latest proxy does not match the
current edit graph hash.

### Remotion / Node

Prefer Node 24 for Remotion CLI:

```json
{
  "mcpServers": {
    "open-edit": {
      "command": "/path/to/open_edit/.venv/bin/open-edit-mcp",
      "args": ["--project", "/absolute/path/to/project"],
      "env": {
        "OPEN_EDIT_NODE_BIN": "/path/to/node24/bin/node",
        "OPEN_EDIT_WHISPER_LANGUAGE": "ar",
        "OPEN_EDIT_WHISPER_MODEL": "small",
        "OPEN_EDIT_INGEST_ALLOWLIST": "/home/you/Videos"
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

- Tools are project-scoped to the pinned directory (plus ingest allowlist).
- `run_script` uses the bwrap sandbox on Linux by default. On Windows it
  defaults to `OPEN_EDIT_SANDBOX_BACKEND=dev` (no jail — rely on the MCP host).
  Explicit `OPEN_EDIT_SANDBOX_BACKEND=bwrap` is rejected on Windows.
- Moviepy `generate_visual_for_segment` requires the Linux render-sandbox
  binary and is unsupported on Windows.
- Prefer an absolute project path in MCP config; do not point at untrusted trees.

## License

MCP itself is free. Remotion licensing (if you use Remotion compositions) is
separate — see [`REMOTION_LICENSE.md`](REMOTION_LICENSE.md).
