# Targeted editing review — 2026-10-09

Reviewed Claude's controllable studio from main `af310a92`, concentrating on
video regions, AI instructions, manual changes after AI edits and agent context
cost. The original implementation plan remains unchanged.

| Finding | Resolution |
| --- | --- |
| A video selection rectangle existed only in browser state. Neither chat nor external MCP received it. | Share a validated region with canvas dimensions and its own frame time through HTTP, chat and persisted workspace focus. A clear button removes it without creating an Undo action. |
| Every context request returned the whole timeline and literal graphics source, including unrelated clips. The built-in prompt also duplicated project state. | Default to a compact target view, selected track/effect metadata and timeline counts. Literal source and the full timeline are explicit expansions. Default MCP JSON is limited to 32 KiB, with collection counts, sections, offsets and omission metadata. |
| Publishing selection/playhead changes replayed the graph and loaded complete source unnecessarily. | Validate and persist focus directly. Graph revision and history stay unchanged; stale browser focus refreshes before retrying. |
| Context read objects and operations from separate snapshots; concurrent edits could cause an inconsistent revision or abort a built-in turn. | Read revision, focus, objects and operations in one SQLite snapshot. Concurrent-write regression proves the old complete snapshot remains usable. |
| Small graphics adjustments required an entire source document round trip. | `edit_project(operation="apply_graphics_edits")` accepts document ID, expected revision and small edits using stable source IDs. Stored JSX is rewritten and committed through the shared lock/history path. |
| Implicit context included marks for unrelated targets and times. | Filter implicit marks by target and time. Explicitly selected marks remain available at other times; hidden marks stay excluded. |
| Built-in prompt examples named the retired run_python tool and an invalid agent operation author. | Align examples with the six public tools, ai/user authors and targeted source edits, reducing avoidable schema failures. |

Compact objects are summaries, not replacement payloads. The context instructs
agents to fetch the complete original with `get_studio` before replacing it.
Source-free graphics changes preserve comments, IDs, trims, effects, locks and
Undo/Redo. The MCP public surface remains six tools.

Measured fixture: 500 media clips, one 105,424-byte editable graphics document,
and one timed instruction. JSON uses the same escaping as MCP output.

| Payload | Before | After |
| --- | ---: | ---: |
| Target context | 266,244 bytes / 64,307 tokens | 3,753 bytes / 1,173 tokens |
| Small title edit | 105,655 bytes / 15,201 tokens | 182 bytes / 54 tokens |
| Median workspace-focus save | 938.71 ms | 1.46 ms |

Token measurements use `cl100k_base` through an instrumentation-only tiktoken
installation. They exclude startup schemas and conversation history and do not
represent measured charges from Claude or another provider. Context generation
still derives the graph: approximately 905 ms versus 921 ms in this fixture.
The main performance gains are reduced agent payloads and cheap focus updates.
Reproduce with `PYTHONPATH=. python tools/benchmark_editing_context.py`;
tiktoken is optional and is not added to application dependencies.

Validation: broad local regression passed 1,693 tests before the final focused
refinements; the final focused suite passed 108 tests. Separate agent/MCP checks
cover the completed changes. Real Playwright studio acceptance passed: media
rectangle coordinates, chat payload, external-agent focus, graphics editing,
manual adjustment after AI work, locks, atomic Undo/Redo, selective request
revert, reopening, interactive/export pixel parity, configurable local export,
and full-quality range rendering. A real stdio MCP client initialized the
six-tool server, read the saved region and committed a small source edit.
The region screenshot was visually inspected. Ruff and JavaScript syntax pass.
Platform and fresh-package acceptance are run by the GitHub workflows.

Selecting a region in imported footage provides a spatial instruction anchored
to a frame, plus the visible clip candidates and source timing. It does not
automatically identify, track or remove real pixel objects. Imported footage
remains referenced media; the compiler represents the editing instructions and
authored graphics as code. Object-relative annotations on authored graphics use
the existing composition transforms. No full-frame screenshot sequence is
needed for the targeted source-edit workflow tested here.

The built-in agent tests use a scripted provider; the real MCP test verifies
transport and tools, not the creative judgment of a live paid model. These
checks establish the tested behavior, not a guarantee that no bugs remain.
