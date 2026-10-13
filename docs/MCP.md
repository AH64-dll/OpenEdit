# OpenEdit MCP

Start a local, project-bound stdio server:

```bash
open-edit-mcp --project /absolute/path/to/project
```

The project must contain `.open_edit`. Use `open_edit init PATH` to create it.
For host settings use `open_edit mcp-config --project PATH --format mcp` (or
`opencode` / `codex`); [connection instructions](agent-configure.md).
No HTTP listener or model key is required by MCP. `open_edit serve` opens the
same data for preview, timeline selection, graphics and export.

## Six composable interfaces

| Tool | Role |
|---|---|
| `query_project` | Timeline, assets, editing context, media inspection and capability help |
| `edit_project` | Project edits and supported creative generation |
| `run_script` | Bounded Python IR editing, validated and committed atomically |
| `trigger_render` | Preview, final output or incremental preview ranges |
| `get_render_job` | Durable job progress and results |
| `cancel_render_job` | Cancel queued or running work |

The default schema/prompt is compact. Nested operation parameters and examples
are retrieved on demand:

```json
{"query":"describe","params":{"name":"apply_studio_changes"}}
```

Without `name`, `describe` lists available queries/operations. `name: "ir"`
describes the Python editing API. Specialized implementations load only when used.

## Precise edits and visual context

`get_editing_context` reports the graph revision, playhead, selection, marks,
stable document/source IDs and relevant clips. Use that revision when committing
source-backed changes; a stale write is rejected without damaging newer work.
`apply_studio_changes` applies documents, captions, annotations and IR operations
as one reversible action. `apply_graphics_edits` updates text/properties by stable
source ID without retrieving an entire source document. In an atomic creation
batch, set track `index` explicitly if ordering matters: the first video track is
the base; subsequent video tracks composite above it.

`inspect_media` supplies bounded timestamped frames/contact sheets and selected
transcript ranges. Ask `describe` for its parameters. MCP supplies actual image
content alongside concise metadata; transcript-only retrieval can request zero
frames. Its content-addressed cache survives reopening. Uniform visual sampling
is not semantic scene detection; choose a narrower range for short events.

Agents choose their creative strategy. The application keeps timing, decoding,
synchronization, revision guards and rendering deterministic. Imported footage
stays referenced media; source-backed geometry is for authored graphics.

## Preview and export

```json
{"mode":"final","encoder":"cpu","wait":false}
```

A nonblocking render returns a `job_id`. Poll with `get_render_job`; inspect the
terminal result and QC report. `wait: true` is available for short workflows.
Timeline preview chunks (`preview_chunks`) prioritize ranges, then fill remaining work in the background.
The UI plays completed ranges and labels stale fallback media explicitly.

Final UI exports capture the selected source revision, retain immutable referenced
media and validate output before publishing a local file. Existing files are not
overwritten. Completed graphics caches are reusable across frozen snapshots;
source/runtime/media changes invalidate their content keys. Browser exports and
MCP rendering use the same media engine.

A successful job alone does not prove model understanding, provider token savings
or every visual decision. Inspect timestamps/images and final media as needed.

## Help and trust

Compact startup guidance is included in MCP `initialize`. Longer playbooks are
available as MCP resources/prompts and in `open_edit/harness_skills`; they are
optional references, not a compulsory file-reading workflow.

MCP is a communication protocol, not isolation. Local import copies readable
absolute media paths into the project's CAS. `run_script` executes trusted Python
with the host account's permissions, bounded timeout and atomic edit validation.
Connect trusted agents and use an explicit project. [Installation](../INSTALL.md)
explains runtime dependencies and optional engine licenses.
