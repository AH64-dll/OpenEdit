# Open Edit Experimental Prototype

This directory is **experimental**. It is not the production implementation of `mlt-pipeline`.

The supported production path for this repository is the Go pipeline in `cmd/`, `internal/`, `run.sh`, and `edit.sh`.

Read the boundary and bridge contract before using this code:

- [`../docs/architecture-boundary.md`](../docs/architecture-boundary.md)

## Status

`open_edit/` contains prototype work for a larger AI-native editor:

- Python IR/edit graph code
- asset storage and render/QC helpers
- FastAPI server and static UI
- sandbox experiments
- LLM provider integrations
- Remotion materializing motion graphics (optional; see
  [`../docs/REMOTION_LICENSE.md`](../docs/REMOTION_LICENSE.md))
- Local MCP server so Cursor (or another agent) can drive Open Edit as a
  plugin — see [`../docs/MCP.md`](../docs/MCP.md)

It may be useful for exploration, but it has a different architecture and maturity level than the Go pipeline.

## Motion graphics backends

| Backend | Op / path | Use for |
|---|---|---|
| MLT / melt | clips on tracks | Timeline A/V |
| HyperFrames | `AddHtmlOverlayOp` | Simple HTML lower thirds |
| Remotion | `AddRemotionCompositionOp` → CAS clip | React motion graphics |
| moviepy templates | `generate_visual_for_segment` | Quick procedural fills |

Remotion compositions are **materialized before emit**, then **ffmpeg-burned**
onto the melt proxy/final (MLT multitrack composite of Remotion is not the
trusted path). They are not HyperFrames overlays.

## Known experimental limits

- **Sandbox:** On Linux, `run_script` needs bwrap/seccomp, or set
  `OPEN_EDIT_SANDBOX_BACKEND=dev` (weaker). On Windows, `dev` is the default
  (no bwrap). Moviepy `generate_visual_for_segment` is Linux-only.
- **Windows MCP:** See [`../docs/MCP.md`](../docs/MCP.md) for native Windows
  install (`.\.venv\Scripts\open-edit-mcp.exe`), `;`-separated ingest
  allowlists, and PATH deps (ffmpeg, melt, Node).
- **Arabic / Whisper:** defaults are `base` + auto language. For Arabic talks:
  `OPEN_EDIT_WHISPER_LANGUAGE=ar` and usually `OPEN_EDIT_WHISPER_MODEL=small`.
- **Local ingest via MCP/agent:** `edit_project operation=ingest_local` with
  absolute paths under the project or `OPEN_EDIT_INGEST_ALLOWLIST`
  (`os.pathsep`-separated roots).
- **Remotion Node:** prefer Node 24 via `OPEN_EDIT_NODE_BIN` (system Node 26
  has bitten the ESM bridge).
- Go pipeline remains the repo production renderer boundary.

## Non-goals while experimental

- Do not make production scripts depend on `open_edit` internals.
- Do not treat `open_edit`'s MLT/rendering code as canonical while the Go CLIs own production rendering.
- Do not mutate Go pipeline artifacts in place from this package.

## Bridge rule

If this prototype needs to interoperate with the production pipeline, use the file-based bridge:

1. Read `metadata.json` and `edl.json` as imported snapshots.
2. Export a new file, for example `edl.open_edit.json`.
3. Validate it through the Go bridge helper:

```bash
scripts/validate_open_edit_edl.sh projects/<name> edl.open_edit.json --render
```

Or run the raw production commands:

```bash
bin/compile --edl edl.open_edit.json --metadata metadata.json --output project.open_edit.mlt
bin/render --mlt project.open_edit.mlt --output preview.open_edit.mp4 --dry-run --timeout 10m
```

Only validated artifacts should be promoted back to `edl.json` or `project.mlt`.
