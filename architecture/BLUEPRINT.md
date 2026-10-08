# Open Edit architecture

The Python package is the product. MCP over stdio is the primary interface.
An external agent owns the creative loop; Open Edit validates edits, stores the
IR and runs rendering against the project pinned when the server starts.
`open_edit serve` starts the review UI. Optional SDK chat requires `--with-agent`.

## Package responsibilities

| Package | Responsibility | Entry points |
|---|---|---|
| `mcp` | Stdio tools, prompts and resources | `server.py`, `adapters.py`, `skills.py` |
| `kernel` | Shared validation, dispatch, edit commands and durable render jobs | `tool_registry.py`, `schema_validator.py`, `tool_executor.py`, `render_jobs.py` |
| `agent/tools` | Editing and analysis implementations | `TOOL_TABLE`, `pyagent_timeline_ops.py` |
| `ir` | Timeline models, replay, derivation and reference validation | `types.py`, `apply.py`, `derive.py`, `validate.py` |
| `storage` | SQLite graphs, assets, notes and caches | `edit_graph.py`, `assets.py`, `paths.py`, `db.py` |
| `render` | MLT timelines, FFmpeg and graphics materialization | `orchestrator.py`, `timeline_plan.py`, `hyperframes.py`, `html_overlay.py` |
| `qc` | Render quality checks | `gate.py`, `black_frames.py`, `frozen_frames.py`, `silence.py` |
| `serve` | Review HTTP/WebSocket routes and optional chat | `app.py`, `routers`, `ws`, `agent` |
| `style` | Confirmed editing preferences | `aggregate.py`, `retrieve.py` |

The CLI supplies local project, ingest, script and render commands.

## Shared contracts

MCP exposes six tools: `query_project`, `edit_project`, `run_script`,
`trigger_render`, `get_render_job`, and `cancel_render_job`. The first three
route through `kernel.tool_executor`; rendering uses the same kernel job
service for MCP, HTTP and optional chat. Argument schemas come from
`kernel.tool_registry` and errors use shared result envelopes.

Generated operations and script results commit through
`EditGraphStore.append_many`: validation, operation inserts, status events and
revision changes succeed or roll back together. References can target earlier
operations in the same batch. Stored graph operations remain replayable.

Render jobs persist in `.open_edit/render_jobs.db`. Equivalent queued/running
requests coalesce only when the graph, mode and render settings match. Each
project serializes its local renders, while a global semaphore bounds work.
Cancellation terminates the render subprocess and shutdown awaits local tasks.

## Context and guides

MCP initialization sends short instructions. Detailed guides are loaded through
prompts or `open-edit://skills/` resources. Asset and transcript queries page
large collections. Optional chat caps verbose tool results before budgeting
history and preserves the current request and complete tool exchanges.
`skills/` contains the canonical guides; `open_edit/harness_skills/` contains
matching packaged copies.

## Dependencies and layering

`tests/test_layering.py` checks that IR does not import the agent, storage,
serve or kernel; kernel and MCP do not import serve; storage does not import
IR mutation APIs. Render depends on storage, and QC can use FFmpeg probing.
`qc.gate.no_word_split_check` remains a public compatibility re-export.

MLT/melt and FFmpeg provide base media rendering. Node.js and the pinned
HyperFrames engine provide new HTML graphics; engine resolution checks the
explicit environment setting, repository installation and PATH. Legacy
Remotion graph operations retain their compatibility renderer.

## Project paths

Use `storage.paths.ProjectPaths` for database, assets and script paths.
Current graphs live at `.open_edit/edit_graph.db`; legacy root databases
remain readable. Notes live at the project root. Assets use the
`.open_edit/assets/<hash-prefix>/<hash>` CAS layout. Review chat history and
cost sidecars are optional and do not participate in MCP startup.
