# Graph Report - mlt-pipeline  (2026-08-01)

## Corpus Check
- 483 files · ~276,298 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 5926 nodes · 12710 edges · 355 communities (290 shown, 65 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 730 edges (avg confidence: 0.54)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `d2f44ebd`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- types.py
- get_slice
- Timeline
- test_serve_projects.py
- NotesStore
- app.py
- Project
- RenderCache
- silence.py
- search_assets
- _overlay
- get_adapter
- eval_scenarios.py
- test_serve_llm_usage.py
- EditGraphStore
- test_tools.py
- IR
- test_serve_pi_bridge.py
- RenderProfile
- llm/__init__.py
- discover_runtimes
- logging_setup.py
- _BaseCLIAdapter
- RenderJobService
- execute_tool
- compact_history
- _fixture
- test_serve_agent_visual_verify.py
- RenderSnapshotStore
- storage/assets.py
- FreeFormResult
- import_asset
- ._conn
- load_llm_config
- TestOperationTypes
- app.js
- test_serve_agent.py
- _contract.py
- NarrativeSegment
- validate_or_error
- diagnostics.py
- stream_chat
- test_serve_env.py
- WordAlignment
- HtmlOverlay
- pi_bridge.py
- tests/test_html_overlay.py
- test_serve_llm_pi.py
- generate_composition_html
- test_serve_errors.py
- test_serve_asset_stream.py
- test_long_form_e2e.py
- _render_spec
- test_visual_verify.py
- run_free_form
- cli.py
- Stabilization Report — 2026-07-24
- test_serve_agent_cost.py
- ensure_remotion_scaffold
- tool_registry.py
- test_providers.py
- test_apply_free_form.py
- test_sandbox_backends.py
- get_asset_or_error
- EffectCatalog
- compute_edit_graph_hash
- showToast
- test_serve_ws.py
- select_encoder
- motion_graphics/templates/__init__.py
- kernel/__init__.py
- TestAssetsAlignment
- bindEvents
- _generate_waveform_inspection_image
- chat.js
- test_agent_loop_stability.py
- package.json
- tool_result
- test_mcp_server.py
- make_error
- transcribe
- test_serve_cost_badge.py
- bridge.py
- run_render
- list_assets
- ProjectPaths
- compress_silence
- _build_system_prompt
- test_opencode_adapter.py
- ensure_schema
- test_transcription_pack.py
- remotion_bridge.mjs
- test_serve_render_jobs.py
- pyagent_search_assets.py
- visual_verify.py
- test_ir_api.py
- test_serve_verify_chip.py
- generate_visual
- materialize.py
- now_iso8601
- _node_harness.py
- orchestrator.py
- melt_runner.py
- test_serve_cost.py
- test_review_ui.py
- AddClipOp
- profiles.py
- _SlowPopen
- AssetStore
- serve/agent/__init__.py
- history_store.py
- cap_tool_result
- boot
- test_phase567_edit_render.py
- test_cli.py
- test_serve_llm_config_api.py
- Asset
- test_serve_chat_status.py
- test_serve_search_assets.py
- staging.py
- ops.py
- TokenAuthMiddleware
- TestPhase1Integrity
- test_frozen_frames.py
- run_trigger_render
- Analysis Report: Automatic 30ms Audio Micro-Fades in MLT Emitter (Milestone 1 / R1)
- _coerce_event
- extension.ts
- routers/projects.py
- Detailed Analysis: 30ms Audio Micro-Fades in MLT Emitter (Milestone 1 / R1)
- pi_extension/package.json
- edit_graph.py
- test_orchestrator_fails_hard_on_remotion_error
- routers/config.py
- save_stored_key
- tool_executor.py
- Milestone 3 Analysis Report: Dual-Panel Waveform Cut Inspection Image Generation
- Milestone 3 Analysis Report: Waveform Cut Inspection Image Generation
- run_qc_gate
- test_serve_loading_state.py
- Open Edit as a local MCP server
- serve/__init__.py
- test_agent_tool_table_coverage.py
- Install Open Edit
- test_sandbox_observations.py
- Handoff Report — Reviewer 1 for Milestone 1 (30ms Audio Micro-Fades)
- analyze
- Deep-Dive Technical Analysis: 30ms Audio Micro-Fades in MLT Emitter
- Milestone 2 (R2): Token-Efficient Phrase-Packed Transcript Tool Analysis
- 3. Confirmed and High-Risk Findings
- _FakePopen
- test_serve_module_structure.py
- list_black_frames
- test_huge_line_stream_no_limit_overrun
- test_timeline_full.py
- get_profile_path
- Checks (and what to do about a failure)
- Render Pipeline Fix — Design (2026-08-01)
- diagnostics
- open_edit/agent/__init__.py
- skills/__init__.py
- motion_graphics/__init__.py
- catalog/__init__.py
- Rules
- qc/__init__.py
- render/__init__.py
- Open Edit MCP — agent playbook
- runtimes/__init__.py
- open_conn
- get_thumbnail
- get_visual_verify_config
- Open Edit MCP — agent playbook
- Phase 6 — Deduplicate Shared Infrastructure
- test_storage/__init__.py
- probe_streams
- open_edit
- Rules
- Phase 1 — Delete Dead Code
- build_prior_state
- test_layering.py
- Target System Architecture
- harness_skills/README.md
- Analysis Report: Token-Efficient Phrase-Packed Transcript Tool (Milestone 2 / R2)
- Phase 5 — Split God Files
- Tool-surface reference — the 4-pillar tools
- Handoff Report — Milestone 3 (R3: Waveform Cut Inspection Image Generation)
- 2. Specific points the graph surfaced (concrete, file-level)
- set_pinned
- Tool-surface reference — the 4-pillar tools
- Real-world failure modes (watch for these)
- Free-form ops & effect catalog — reference
- capture_hint
- 5. Execution Phases
- Phase 4 (cont.) — Tool Contract
- Free-form ops & effect catalog — reference
- Open Edit MCP reference
- Checks (and what to do about a failure)
- Remotion motion graphics in Open Edit
- Open Edit MCP reference
- OpenEdit Code Restructure Implementation Plan
- Phase 2 — Fix Layering
- Phase 7 — Wire Orphaned Features + Final Polish
- Open Edit Blueprint (fixed)
- BRIEFING — 2026-07-23T13:32:22+03:00
- Remotion motion graphics in Open Edit
- Phase 0 — Stop the Bleeding (P0 runtime bugs)
- Phase 3 — Single Dispatcher, Single Validators
- Open Edit
- Open Edit harness skills
- Remotion Licensing for Open Edit
- test_run_trigger_render_returns_render_failed_on_nonzero_exit
- _looks_like_bwrap_unavailable
- routers/__init__.py
- ws/__init__.py
- 1. Observation
- BRIEFING — 2026-07-23T13:36:25Z
- BRIEFING — 2026-07-23T13:44:00Z
- BRIEFING — 2026-07-23T13:39:00Z
- BRIEFING — 2026-07-23T13:41:00Z
- BRIEFING — 2026-07-23T13:49:00+03:00
- AddRemotionCompositionOp
- OpenEdit_Repair_Plan.md
- Forensic Audit Report — Milestone 4 (Forensic Audit Gate)
- BRIEFING — 2026-07-23T13:49:06Z
- BRIEFING — 2026-07-23T13:47:23Z
- Handoff Report: Milestone 1 (R1: 30ms Audio Micro-Fades in MLT Emitter)
- Handoff Report: 30ms Audio Micro-Fades in MLT Emitter (Milestone 1 / R1)
- BRIEFING — 2026-07-23T10:37:46Z
- BRIEFING — 2026-07-23T13:37:30Z
- BRIEFING — 2026-07-23T13:40:40+03:00
- BRIEFING — 2026-07-23T13:40:05Z
- BRIEFING — 2026-07-23T10:45:00Z
- renderTimeline
- Render Pipeline Fix Implementation Plan
- BRIEFING — 2026-07-23T10:52:47Z
- Original User Request
- Handoff Report — Milestone 4 (Full Test Suite Regression Verification)
- Handoff Report: Milestone 2 (R2: Token-Efficient Phrase-Packed Transcript Tool)
- BRIEFING — 2026-07-23T13:56:20Z
- state.js
- pyagent_generate_remotion_composition.py
- Original User Request
- BRIEFING — 2026-07-23T13:32:15+03:00
- BRIEFING — 2026-07-23T10:34:25Z
- BRIEFING — 2026-07-23T10:35:10Z
- BRIEFING — 2026-07-23T10:32:44Z
- BRIEFING — 2026-07-23T10:36:15Z
- BRIEFING — 2026-07-23T10:37:00Z
- BRIEFING — 2026-07-23T10:38:50Z
- BRIEFING — 2026-07-23T10:37:40Z
- Project: Open Edit Features Implementation
- sample_frames
- Milestones
- Milestone 2 (R2): Token-Efficient Phrase-Packed Transcript Tool Handoff Report
- Summary of Fixes — Worker 1 Fix Agent (Milestone 1)
- .open-edit-launcher.sh
- test_pillar_headers.py
- Current System Architecture (2026-07-25)
- Soft Handoff Report — Project Orchestrator (Gen 1 -> Gen 2)
- Milestone 4 Verification (Run 2) Handoff Report
- Handoff Report: Milestone 1 (Explorer 3 - Corner Cases & Test Implementation)
- Handoff Report: Milestone 3 (R3: Waveform Cut Inspection Image Generation)
- Handoff Report: Waveform Cut Inspection Edge Case Analysis & Unit Test Strategy (Milestone 3 / R3)
- Handoff Report — Reviewer 2 (Milestone 1: 30ms Audio Micro-Fades in MLT Emitter)
- Handoff Report — Milestone 2 Review (Token-Efficient Phrase-Packed Transcript Tool)
- Summary of Changes
- Handoff Report — Worker 1 Fix Agent (Milestone 1)
- Handoff Report — Milestone 1 (R1: Automatic 30ms Audio Micro-Fades in MLT Emitter)
- Handoff Report: Milestone 2 (R2: Token-Efficient Phrase-Packed Transcript Tool)
- Handoff Report — Milestone 3 (R3: Waveform Cut Inspection Image Generation)
- Handoff Report — Victory Auditor
- Handoff Report — worker_m4_fix
- Style memory
- Style memory
- Delivery Loop — Grok Orchestrator
- Progress Tracking — Open Edit Features
- Changes Summary — Milestone 3 (R3: Waveform Cut Inspection Image Generation)
- test_free_form_e2e.py
- 7. First Implementation Batch
- Changes Summary - Milestone 2 (Token-Efficient Phrase-Packed Transcript Tool)
- Victory Auditor Progress
- Phase 1 — Unify Providers, Models, Capabilities, and Keys
- Phase 10 — CI, Release Gates, and Documentation
- Phase 0 — Freeze Scope and Build a Reproduction Baseline
- Phase 2 — Repair the Agent and Tool Protocol
- test_render_composited_returns_final_path_on_success
- test_serve_send_reconnect.py
- Progress Log - reviewer_m4_2
- Progress — Milestone 3 Worker 3
- Original Request
- Phase 3 — Secure and Stabilize HTTP/WebSocket Boundaries
- Phase 4 — Repair Project Creation and Media Ingestion
- Phase 8 — Integrate the Go and Python Paths
- test_run_trigger_render_overlay_inside_running_loop
- auditor_m4/ORIGINAL_REQUEST.md
- auditor_m4/progress.md
- PROGRESS.md
- run_loop.sh
- reviewer_m4_2/ORIGINAL_REQUEST.md
- reviewer_m4/ORIGINAL_REQUEST.md
- reviewer_m4/progress.md
- teamwork_preview_explorer_m1_1/ORIGINAL_REQUEST.md
- teamwork_preview_explorer_m1_1/progress.md
- teamwork_preview_explorer_m1_2/ORIGINAL_REQUEST.md
- teamwork_preview_explorer_m1_2/progress.md
- teamwork_preview_explorer_m1_3/ORIGINAL_REQUEST.md
- teamwork_preview_explorer_m2_1/ORIGINAL_REQUEST.md
- teamwork_preview_explorer_m2_1/progress.md
- teamwork_preview_explorer_m2_2/ORIGINAL_REQUEST.md
- teamwork_preview_explorer_m2_2/progress.md
- teamwork_preview_explorer_m3_1/ORIGINAL_REQUEST.md
- teamwork_preview_explorer_m3_1/progress.md
- teamwork_preview_explorer_m3_2/ORIGINAL_REQUEST.md
- teamwork_preview_explorer_m3_2/progress.md
- teamwork_preview_reviewer_m1_1/ORIGINAL_REQUEST.md
- teamwork_preview_reviewer_m1_1/progress.md
- teamwork_preview_reviewer_m1_2/ORIGINAL_REQUEST.md
- teamwork_preview_reviewer_m1_2/progress.md
- teamwork_preview_reviewer_m2_1/ORIGINAL_REQUEST.md
- teamwork_preview_reviewer_m2_1/progress.md
- teamwork_preview_reviewer_m2_2/ORIGINAL_REQUEST.md
- teamwork_preview_reviewer_m2_2/progress.md
- teamwork_preview_reviewer_m3_1/ORIGINAL_REQUEST.md
- teamwork_preview_reviewer_m3_1/progress.md
- teamwork_preview_worker_m1_fix/ORIGINAL_REQUEST.md
- teamwork_preview_worker_m1/ORIGINAL_REQUEST.md
- teamwork_preview_worker_m1/progress.md
- teamwork_preview_worker_m2/ORIGINAL_REQUEST.md
- teamwork_preview_worker_m2/progress.md
- teamwork_preview_worker_m3/ORIGINAL_REQUEST.md
- worker_m4_fix/ORIGINAL_REQUEST.md
- worker_m4_fix/progress.md
- .open-edit-stop.sh
- test_render_composited_unlinks_partial_final_mp4_on_failure
- test_root_has_data_no_timeline_attribute
- test_root_has_proper_html_document_structure
- test_one_overlay_produces_single_clip_div
- test_track_assignment_non_overlapping_shares_index
- test_non_primitive_variable_raises_overlay_render_error
- test_template_path_rejects_symlink_escape
- test_render_composited_writes_composition_html_to_compositions_subdir
- test_render_composited_cleans_up_composition_html_on_success
- test_render_composited_cleans_up_composition_html_on_failure
- test_search_assets_openverse_ranks_cc0_and_plain_by

## God Nodes (most connected - your core abstractions)
1. `EditGraphStore` - 227 edges
2. `AddClipOp` - 168 edges
3. `Timeline` - 159 edges
4. `Project` - 134 edges
5. `apply_operation()` - 93 edges
6. `AssetStore` - 83 edges
7. `Asset` - 79 edges
8. `derive_timeline()` - 73 edges
9. `IR` - 71 edges
10. `new_id()` - 66 edges

## Surprising Connections (you probably didn't know these)
- `test_header_auto_inject_missing()` --indirect_call--> `run_free_form()`  [INFERRED]
  tests/test_pillar_headers.py → open_edit/agent/sandbox/bridge.py
- `test_run_python_importable()` --indirect_call--> `run_python()`  [INFERRED]
  tests/test_pillar_headers.py → open_edit/agent/tools/pyagent_run_python.py
- `test_run_python_importable()` --indirect_call--> `run_python()`  [INFERRED]
  tests/test_pillar_tools.py → open_edit/agent/tools/pyagent_run_python.py
- `test_narrative_segment_pydantic()` --calls--> `NarrativeSegment`  [EXTRACTED]
  tests/test_skill/test_narrative_analyzer.py → open_edit/agent/skills/narrative_analyzer.py
- `test_apply_free_form_code_appends_child_ops()` --calls--> `new_id()`  [INFERRED]
  tests/test_apply_free_form.py → open_edit/ir/ids.py

## Import Cycles
- 3-file cycle: `open_edit/serve/agent/__init__.py -> open_edit/serve/agent/cli_turn.py -> open_edit/serve/agent/loop.py -> open_edit/serve/agent/__init__.py`

## Communities (355 total, 65 thin omitted)

### Community 0 - "types.py"
Cohesion: 0.11
Nodes (73): Bootstrap codegen: render ``_bootstrap.py`` for in-sandbox execution.  C2 prefer, Protocol, In-process IR API for free-form Python code (sandbox side).  Phase 3 Task 4: rea, Anything with a single-arg `append` (list, _FlushingBuffer, ...)., SupportsAppend, ChangeClipSpeedOp, FreeFormCodeOp, GroupEditsOp (+65 more)

### Community 1 - "get_slice"
Cohesion: 0.19
Nodes (15): Phase 4 T2: Style Memory (aggregate, retrieve, style_inject)., get_slice(), _load_profile(), Any, Tag-gated style profile retrieval for system prompt injection.  Per phase4-desig, _trim_to_token_cap(), Phase 4 Task 3: tag-gated style profile retrieval., Per spec section 8.8: below confidence 0.2, category is omitted. (+7 more)

### Community 2 - "Timeline"
Cohesion: 0.06
Nodes (96): _Element, apply_operation(), _apply_normalize_audio(), _apply_set_audio_gain(), Audio operations: gain and normalize. Pure functions., Add a 'volume' effect tagged with the target_dbfs to the target.      Without a, _apply_change_clip_speed(), _apply_replace_clip_source() (+88 more)

### Community 3 - "test_serve_projects.py"
Cohesion: 0.07
Nodes (46): create_project(), Create and validate a project before publishing it to the projects root.      A, list_assets_from_disk(), Read all asset sidecar JSONs from <project>/assets/., _make_real_asset(), _make_real_note(), _make_real_op(), _make_real_project() (+38 more)

### Community 4 - "NotesStore"
Cohesion: 0.10
Nodes (36): pyagent_add_marker: agent-initiated flag, writes to NotesStore with source=agent, cmd_notes_add(), `open_edit notes add` — append a note to a project (M1)., CreateNoteRequest, CreateProjectRequest, BaseModel, NoteSource, NotesStore (+28 more)

### Community 5 - "app.py"
Cohesion: 0.07
Nodes (40): FastAPI, _lifespan(), FastAPI app for the Open Edit server.  Routes ------ - ``GET  /api/projects``, _is_localhost_websocket(), WebSocket, Authentication, WebSocket auth, and rate limiting for the Open Edit server.  Ext, Validate remote chat connections before ``accept()``.      HTTP middleware does, _websocket_auth_error() (+32 more)

### Community 6 - "Project"
Cohesion: 0.04
Nodes (84): derive_timeline(), Replay all non-reverted, applied operations in sequence order.      When ``stric, AddEffectOp, Project, _effects_for_clip(), _get_default_catalog(), _known_clip_ids(), _known_effect_ids() (+76 more)

### Community 7 - "RenderCache"
Cohesion: 0.10
Nodes (31): cache_ttl_sec(), canonical_json_hash(), Any, Path, Filesystem-backed render cache, keyed by the edit-graph hash.  Single hash autho, Deprecated compatibility shim: use ``compute_edit_graph_hash``.      Retained on, Cache key = graph hash + profile identity (resolution/quality/overrides/encoder), Freshness window from ``OPEN_EDIT_RENDER_CACHE_TTL_SEC`` (default 24h). (+23 more)

### Community 8 - "silence.py"
Cohesion: 0.10
Nodes (31): AudioLevels, _ffmpeg(), get_audio_levels(), _has_audio_stream(), _last_stderr_line(), list_silence(), _parse_db(), _parse_overall_db() (+23 more)

### Community 9 - "search_assets"
Cohesion: 0.06
Nodes (46): _cache_key(), _freesound_api_key(), Search Pexels / Freesound for stock media matching ``args['query']``.      The `, search_assets(), Tests for ``open_edit.agent.tools.pyagent_search_assets``.  The tool dispatches, Video without the Pexels key returns a structured error naming the     missing e, Without Freesound, audio uses the keyless Openverse fallback., An unknown ``kind`` is rejected up front (no API call made). (+38 more)

### Community 10 - "_overlay"
Cohesion: 0.06
Nodes (45): _overlay(), skipif, Sibling-task cancellation: when a non-OverlayRenderError exception is raised, Build a minimal HtmlOverlay-shaped object for the composition tests., Sibling-task cancellation: when comp_html_task raises unexpectedly, the     orch, Persistent tmpdir cleanup: on overlay/subprocess failure, bg.mp4 is preserved, Test 1: root has data-composition-id, data-start=0, data-duration=<bg_total>,, Test 5: clip div's data-start/data-duration/data-track-index     match the HtmlO (+37 more)

### Community 11 - "get_adapter"
Cohesion: 0.08
Nodes (33): get_adapter(), list_adapters(), _opencode_models_via_cli(), v1.7 — CLI adapter interface.  A ``CLIAdapter`` is a thin facade over a single C, Run ``opencode models`` and return the list of model ids.      Cached for 60s. I, Shell out to ``opencode models`` for live discovery., Look up an adapter by name. Raises ``KeyError`` on unknown., Return the names of all registered adapters (sorted). (+25 more)

### Community 12 - "eval_scenarios.py"
Cohesion: 0.07
Nodes (52): _clip(), _derive(), _project(), Scenario Evaluation Suite for Open Edit — Phase 7.  Tests the IR/apply layer aga, Add then remove a clip, assert track is empty., Add clip then move it to a new position, assert new position., Add clip then trim in/out points, assert new in/out., Add clip then slip it, assert result stays within original bounds. (+44 more)

### Community 13 - "test_serve_llm_usage.py"
Cohesion: 0.05
Nodes (39): _pi_extension_path(), Default: <open_edit>/serve/pi_extension/extension.ts, _collect(), fake_anthropic_sdk(), fake_pi_with_usage(), _FakeAnthropicClient, _FakeAnthropicFinalMessage, _FakeAnthropicMessages (+31 more)

### Community 14 - "EditGraphStore"
Cohesion: 0.06
Nodes (28): is_verify_disabled(), Path, Per-project metadata accessors for the open_edit server.  v1.5 added the ``verif, Return True if the project's ``verify_disabled`` flag is set.      Reads from th, EditGraphStore, Record a command for idempotency. No-op if command_id exists., Return True if a command with the given id has been recorded., Mark a command as finished with a status and optional result. (+20 more)

### Community 15 - "test_tools.py"
Cohesion: 0.07
Nodes (60): add_marker(), Append a ReviewNote with source=agent at the given timestamp., get_pending_notes(), List pending notes. Default: first 10 full + count of rest., get_style_profile(), Return the style profile slice for ``args['op_type']``.      Args:         args:, propose_silence_cuts(), Return silence-cut suggestions for ``args['asset_hash']``.      Args:         ar (+52 more)

### Community 16 - "IR"
Cohesion: 0.08
Nodes (29): IR, Any, Free-form Python IR API. Each method appends one Pydantic op to the buffer., Append AddRemotionCompositionOp; return composition_uid., Append AddHtmlOverlayOp; return overlay_id., Caller-supplied value wins; else fall back to the IR-level value., Append AddClipOp; return generated clip_id., new_id() (+21 more)

### Community 17 - "test_serve_pi_bridge.py"
Cohesion: 0.06
Nodes (43): _bootstrap_project(), _bridge_env(), Path, Tests for ``open_edit.serve.pi_bridge``.  The bridge is the Python CLI that the, Nonexistent project path → structured error., Full add_marker + get_pending_notes roundtrip on a real project., The bridge auto-injects project_id (from EditGraphStore) when     the caller did, ``--list-tools`` returns the 6 advertised tool names. (+35 more)

### Community 18 - "RenderProfile"
Cohesion: 0.09
Nodes (21): _allowlist_roots(), MeltRunner, CompletedProcess, Path, Build and run melt commands, mediating the render cache.      Cache lookup happe, Look up a cached render for ``key`` (None if absent)., True if the cached file is younger than the cache freshness window., Copy ``source_path`` into the cache under ``key``. Returns the cached path. (+13 more)

### Community 19 - "llm/__init__.py"
Cohesion: 0.11
Nodes (33): Any, Generic subprocess driver for CLI providers (pi, opencode, antigravity, jcode) +, Generic subprocess driver for any CLIAdapter (pi, opencode, ...).      Builds th, Pi provider — delegates to _stream_cli with the PiAdapter.      After _stream_cl, _stream_cli(), _stream_pi(), CLI-provider streaming: generic driver + pi wrapper., _message_plain_text() (+25 more)

### Community 20 - "discover_runtimes"
Cohesion: 0.14
Nodes (20): candidate_dirs(), discover_runtimes(), find_binary_in_expanded_path(), get_expanded_path_env(), Any, Path, v1.8 — Runtime Registry & GUI PATH Expansion.  All provider metadata is defined, Specification and status of an LLM runtime.      Fields are derived from the can (+12 more)

### Community 21 - "logging_setup.py"
Cohesion: 0.06
Nodes (43): Logger, LogRecord, bind_context(), ContextFilter, CorrelationIdMiddleware, get_context(), get_conversation_id(), get_job_id() (+35 more)

### Community 22 - "_BaseCLIAdapter"
Cohesion: 0.05
Nodes (21): _AnthropicAdapter, _AntigravityAdapter, _BaseCLIAdapter, CLIAdapter, _JCodeAdapter, _normalize_pi_object(), _OpenAIAdapter, _OpenCodeAdapter (+13 more)

### Community 23 - "RenderJobService"
Cohesion: 0.12
Nodes (22): JobStatus, Connection, Path, Row, Mark jobs interrupted by a prior service process as orphaned., Return (revision, hash, timeline_status) for the current edit graph., Run the deterministic QC gate on a finished render and attach the         report, Run the canonical Python CLI (or overlay bridge) and consume JSON. (+14 more)

### Community 24 - "execute_tool"
Cohesion: 0.09
Nodes (39): LookupError, execute_tool(), Raised by :func:`execute_tool` when the named tool is not     registered in ``op, Run a tool by name, dispatching through     ``open_edit.agent.tools.TOOL_TABLE``, ToolNotFound, project_path(), Path, Server-side tool-execution idempotency (Phase 1: data integrity).  A re-delivere (+31 more)

### Community 25 - "compact_history"
Cohesion: 0.10
Nodes (31): compact_history(), ContextBudget, count_tokens(), count_tokens_history(), count_tokens_message(), _has_tool_result(), Any, Token counting and sliding-window history truncation for context budget manageme (+23 more)

### Community 26 - "_fixture"
Cohesion: 0.13
Nodes (31): build_pipe_commands(), _fps_string(), overlay_filter_chain(), OverlayClip, Path, Frame-server pipe: melt -> rawvideo stdout -> ffmpeg single encode.  melt compos, Build melt-video, melt-audio, and ffmpeg commands for one render., Filter-graph fragments for the overlay burn (pure; formerly the     ``burn_overl (+23 more)

### Community 27 - "test_serve_agent_visual_verify.py"
Cohesion: 0.10
Nodes (40): _fake_mp4(), _make_fake_project_state(), _make_mock_stream(), _patched_agent_with_render(), Any, asyncio, Path, v1.5: visual verification loop in the agent.  These tests exercise the new verif (+32 more)

### Community 28 - "RenderSnapshotStore"
Cohesion: 0.08
Nodes (27): Path, Render snapshot recording into the RenderSnapshotStore (Phase 4 T4)., Resolve the SQLite path for a project's render snapshots.      Mirrors the chat-, Append a snapshot to the RenderSnapshotStore.      ``success=True`` records a `r, record_snapshot(), _snapshots_path(), BaseModel, Enum (+19 more)

### Community 29 - "storage/assets.py"
Cohesion: 0.15
Nodes (9): _hash_file(), _probe_media(), Path, Content-addressed asset store with ffprobe metadata.  Layout: <assets_dir>/<sha2, Path to the metadata sidecar JSON next to the CAS file., Ingest one or more files. Returns one Asset per input path.          Bug B regre, Rewrite an asset's sidecar with new word-level ``alignment``.          Used by b, Compute SHA-256 of a file as a hex string. (+1 more)

### Community 30 - "FreeFormResult"
Cohesion: 0.07
Nodes (34): FreeFormResult, Result of a free-form Python run. Always returned, never raised.      success=Tr, Path, Execute the run and return a FreeFormResult (may raise         SandboxUnavailabl, H5: resolve at call time, not at module import.      P8: resolve via an absolute, H5: resolve at call time, not at module import.      The allow-list is three fix, H5: resolve at call time, not at module import.      Order matches the install c, resolve_binary() (+26 more)

### Community 31 - "import_asset"
Cohesion: 0.06
Nodes (55): _cache_result_path(), _http_download(), import_asset(), _is_allowed_source_url(), _is_private_or_local_host(), _lookup_result(), _open_url(), Any (+47 more)

### Community 32 - "._conn"
Cohesion: 0.11
Nodes (12): Any, Connection, OperationUnion, Return the project_meta table as a dict. Empty if no rows.          JSON-encoded, Set a single project_meta field. Persists immediately.          Non-string value, Append an operation. Returns the assigned sequence_num.          Validates the o, Load all operations in sequence_num order.          Each op carries its ``sequen, Update an operation's status (e.g. for undo/revert or supersede). (+4 more)

### Community 33 - "load_llm_config"
Cohesion: 0.12
Nodes (34): _atomic_write_text(), LLMConfig, LLMConfigError, load_llm_config(), Any, BaseModel, Exception, field_validator (+26 more)

### Community 34 - "TestOperationTypes"
Cohesion: 0.07
Nodes (4): Bug A4: ``rate`` must be > 0 (a 0 or negative rate would crash at render)., Bug A4: ``target_dbfs`` must be in [-100, 0] dBFS., Test suite for Pydantic operation types and helpers., TestOperationTypes

### Community 35 - "app.js"
Cohesion: 0.11
Nodes (27): applyTheme(), autoGrowInput(), cancelTurn(), COMMANDS, fetchLLMConfig(), filteredCommands, handleSend(), initTheme() (+19 more)

### Community 36 - "test_serve_agent.py"
Cohesion: 0.09
Nodes (30): _mock_execute_tool(), _mock_stream_chat(), Any, asyncio, Path, Tests for ``open_edit.serve.agent``.  Mocks the LLM (``stream_chat``) and the to, Full 2-turn conversation: user → tool → final text., A non-conforming chat adapter cannot turn an edit request into a mutation. (+22 more)

### Community 37 - "_contract.py"
Cohesion: 0.11
Nodes (25): Canonical tool result contract.  Every agent tool wrapper returns one of three s, get_asset_store(), _project_root(), Path, Shared helpers for the agent tool wrappers.  Path resolution (``_project_root``,, Return the AssetStore rooted at <project>/.open_edit/assets., Return the project ROOT directory (the folder that contains     ``.open_edit/``), ingest_local() (+17 more)

### Community 38 - "NarrativeSegment"
Cohesion: 0.21
Nodes (17): NarrativeSegment, BaseModel, place(), BaseModel, SFX placer skill: place sound effects at narrative beat transitions.  Per phase4, Place duration-fit SFX at transitions, aligned to music when possible., SfxClip, _load_sfx_library() (+9 more)

### Community 39 - "validate_or_error"
Cohesion: 0.10
Nodes (29): _check_type(), Any, ValueError, Hand-rolled schema validation for Open Edit tool arguments.  Validates tool argu, Return an error dict if validation fails, or None if valid., Raised when tool arguments don't match the schema., Check that ``value`` matches ``expected_type``.      ``number`` accepts both ``i, Validate ``args`` against the schema for ``name``.      Raises ``SchemaValidatio (+21 more)

### Community 40 - "diagnostics.py"
Cohesion: 0.09
Nodes (36): _chromium_available(), collect_diagnostics(), _config_summary(), _disk_free_bytes(), get_health(), _mlt_available(), System health & diagnostics collection for the open_edit server.  Provides three, Return actionable, redacted details about the selected sandbox. (+28 more)

### Community 41 - "stream_chat"
Cohesion: 0.11
Nodes (31): Stream an LLM response as a sequence of :class:`StreamEvent`.      ``messages``, stream_chat(), fake_opencode(), fake_opencode_hang(), asyncio, MonkeyPatch, Path, End-to-end tests for the v1.7 opencode provider (track C). (+23 more)

### Community 42 - "test_serve_env.py"
Cohesion: 0.11
Nodes (17): Tests for ``open_edit.serve.serve_env``.  The module exposes typed config dictio, When the env var is set, ``hyperframes_bin`` is the env value     (no fallback t, OPEN_EDIT_HYPERFRAMES_BIN unset → ``hyperframes_bin`` is ``None``.      Sentinel, OPEN_EDIT_HYPERFRAMES_BIN=/foo/bar → returned verbatim., OPEN_EDIT_OVERLAY_TMPDIR unset → ``overlay_tmpdir`` is ``None``., OPEN_EDIT_OVERLAY_TMPDIR=/tmp/x → Path('/tmp/x').resolve()., OPEN_EDIT_HYPERFRAMES_TIMEOUT_SECONDS defaults to 3600 (int)., OPEN_EDIT_HYPERFRAMES_TIMEOUT_SECONDS=300 → 300. (+9 more)

### Community 43 - "WordAlignment"
Cohesion: 0.11
Nodes (33): find_silence_gaps(), no_word_split_check(), propose_cuts(), Silence cutter skill: propose cuts at silence gaps.  Per phase4-design-revised.m, Check if a cut at [t_start, t_end] splits any word.      A cut splits a word if, Find silence intervals >= ``threshold_ms`` in source time.      Returns a list o, Return gap-based cut suggestions for `asset`.      Each suggestion is a dict::, WordAlignment (+25 more)

### Community 44 - "HtmlOverlay"
Cohesion: 0.09
Nodes (23): AddHtmlOverlayOp, HtmlOverlay, Add an HTML/CSS/JS overlay (e.g. lower-third, title card, caption) that     will, Remove a previously added HTML overlay by its overlay_id., A rendered HTML/CSS/JS overlay composited on top of the video track.      Produc, RemoveHtmlOverlayOp, Add then remove HTML overlay, assert empty., scenario_html_overlay_removed() (+15 more)

### Community 45 - "pi_bridge.py"
Cohesion: 0.26
Nodes (12): _emit(), _emit_error(), main(), Any, Path, Python bridge between the pi extension and ``open_edit.agent.tools``.  The TypeS, Print a JSON object to stdout, flush, exit 0., Print a structured error to stdout, exit 0 (so the TS layer sees     the error i (+4 more)

### Community 46 - "tests/test_html_overlay.py"
Cohesion: 0.09
Nodes (21): v1.6: tests for the HTML overlay compositing module.  The module is split into 4, V2: render_overlay_layer.should_cancel must be Callable[[], bool] | None., V2: composite_with_background.should_cancel must be Callable[[], bool] | None., V2: _run_subprocess_with_cancel.should_cancel must be Callable[[], bool] | None., Pinned `node_modules/.bin/hyperframes` exists → it's returned, no warning., Test 24: FileNotFoundError → OverlayRenderError., No pinned binary → bare `npx hyperframes`, WARNING logged with the prescribed me, Test 34: 3 GB estimate → OverlayRenderError (no subprocess spawned). (+13 more)

### Community 47 - "test_serve_llm_pi.py"
Cohesion: 0.09
Nodes (26): _pi_binary(), _pi_normalize_event(), _PiAdapter, Compat: normalize one parsed pi JSON object (dict → events).      Kept as a modu, _collect(), fake_pi(), Tests for the ``pi`` provider in ``open_edit.serve.llm``.  We don't actually spa, Drop a fake `pi` script in tmp_path and point OPEN_EDIT_PI_BINARY at it. (+18 more)

### Community 48 - "generate_composition_html"
Cohesion: 0.10
Nodes (31): _assign_tracks(), _clip_id(), composite_with_background(), _disk_footprint_check(), _estimate_overlay_size_mb(), generate_composition_html(), _inline_variables(), OverlayRenderError (+23 more)

### Community 49 - "test_serve_errors.py"
Cohesion: 0.07
Nodes (34): projects_root_tmp(), asyncio, parametrize, SimpleNamespace, Tests for the v1.4 fast-fail readable-error contract.  Background (P0-1 in v1.4, GET /api/projects/{id} for a freshly-initialised project returns     the empty s, Connecting a WS to an unknown project sends an error event whose     message inc, When ``OPEN_EDIT_LLM_API_KEY`` is unset, ``stream_chat`` emits a     single ``er (+26 more)

### Community 50 - "test_serve_asset_stream.py"
Cohesion: 0.07
Nodes (32): ffprobe_available(), projects_root_tmp(), Path, Tests for asset streaming in the Open Edit server.  Pins down v1.4 P0-2: a fresh, ``GET /api/projects/{id}`` returns assets whose ``url`` field     points at the, A GET on the asset's ``url`` returns the file with the right     ``Content-Type`, An mp4 asset served via the streaming route has     ``Content-Type: video/mp4``, A Range request returns 206 Partial Content with the right     ``Content-Range`` (+24 more)

### Community 51 - "test_long_form_e2e.py"
Cohesion: 0.12
Nodes (25): BaseException, MusicTrack, BaseModel, Music selector skill: pick mood-matched tracks for narrative segments.  Per phas, Pick tracks using mood first and duration fit as a tie-breaker., Return a modest energy prior used only to break equal-fit ties., select(), _target_energy() (+17 more)

### Community 52 - "_render_spec"
Cohesion: 0.11
Nodes (28): _argv_of(), _make_popen_mock(), Build a minimal RenderSpec-shaped dict for the composition tests., Return the argv list from a mocked subprocess.Popen call., Build a fake Popen instance for the cancellation-aware wrappers., Test 19: subprocess.Popen is called with shell=False (explicit)., Test 20: argv contains '--format mov' (not '--format mp4' or '--transparent')., Test 21: argv contains '-c' (not '--input' which doesn't exist). (+20 more)

### Community 53 - "test_visual_verify.py"
Cohesion: 0.05
Nodes (61): build_qc_evidence(), build_verification_tool_result(), encode_jpeg(), model_capability(), parse_verdict(), Any, Path, Extract a single frame from ``input_path`` to ``output_path`` as JPEG,     downs (+53 more)

### Community 54 - "run_free_form"
Cohesion: 0.06
Nodes (42): _coerce_positive_int(), Run free-form Python in the sandbox. NEVER raises (C7).      `originating_note_i, Normalize an integer limit without allowing malformed values through., run_free_form(), skipif, L3: a free-form script that raises an exception does NOT corrupt the graph., L1: ro-bound source raises OSError(EROFS). The script catches the     error and, The design's "Done when" criterion: 50-line script -> 50 child ops. (+34 more)

### Community 55 - "cli.py"
Cohesion: 0.10
Nodes (37): cmd_free_form(), cmd_init(), cmd_list(), cmd_mcp(), cmd_notes(), cmd_notes_dismiss(), cmd_notes_list(), cmd_render() (+29 more)

### Community 56 - "Stabilization Report — 2026-07-24"
Cohesion: 0.06
Nodes (32): 10. Root Cause Resolution, 11. Repair Batch Update — 2026-07-25, 12. Repair Batch Update — 2026-07-25 (OE-P1-007), 13. Repair Batch Update — 2026-07-25 (Phases 5/6/7), 1. Architecture Chosen, 2. Fixed Issues, 3. Files and Schemas Changed, 4. Provider Capability Matrix (+24 more)

### Community 57 - "test_serve_agent_cost.py"
Cohesion: 0.08
Nodes (29): _mock_stream_chat_with_usage(), Tests for v1.4 P1-3 cost-update plumbing in ``open_edit.serve.agent``.  The agen, The sidecar lives at ``<project>/.open_edit/cost.json`` —     alongside the conv, Return a stream_chat mock that yields the given usage events     before yielding, When the LLM yields a ``usage`` event, the agent loop must     emit a ``cost_upd, A turn that loops through multiple LLM calls (model calls a     tool, gets the r, After the turn, the sidecar JSON at     ``<project>/.open_edit/cost.json`` must, Turn 1: $0.005 cost, persisted. Turn 2: $0.003 cost. The     cost_update for tur (+21 more)

### Community 58 - "ensure_remotion_scaffold"
Cohesion: 0.23
Nodes (14): ensure_remotion_scaffold(), Path, Frozen Remotion starter copied into each project's `.open_edit/remotion/`., Create the Remotion starter under ``.open_edit/remotion`` if missing., Return validation errors for AI-written Remotion TSX/TS source., Write a composition file after path + source validation., validate_composition_source(), write_composition_file() (+6 more)

### Community 59 - "tool_registry.py"
Cohesion: 0.12
Nodes (18): build_tool_schemas(), CancelRenderJobArgs, EditProjectArgs, GetRenderJobArgs, BaseModel, QueryProjectArgs, Pydantic-backed registry of Open Edit tool argument schemas.  Single source of t, Return Anthropic-shaped tool schemas generated from the registry. (+10 more)

### Community 60 - "test_providers.py"
Cohesion: 0.06
Nodes (46): _anthropic_stream(), list_provider_ids(), list_provider_specs(), list_visible_providers(), _openai_stream(), _pi_stream(), provider_default_model(), ProviderSpec (+38 more)

### Community 61 - "test_apply_free_form.py"
Cohesion: 0.21
Nodes (11): Free-form script execution entry point (agent layer).  Task 2.3: moved from `ope, Run a free-form Python script in the sandbox and append its child ops.      Each, run_free_form_code(), minimal_project(), Task 2.3: run_free_form_code integration in agent/free_form.py.  Moved from open, Mocked sandbox returns 3 child ops; they are appended to the project., Sandbox returns failure → ApplyError; edit_graph unchanged., timeout_sec and mem_mb from the op are forwarded to run_free_form. (+3 more)

### Community 62 - "test_sandbox_backends.py"
Cohesion: 0.10
Nodes (34): BwrapBackend, DevSubprocessBackend, get_sandbox_backend(), Exception, Free-form sandbox execution backends.  ``get_sandbox_backend()`` selects the bac, 5b: make a string safe to surface in a result detail.      - Take only the first, Pluggable execution backend for a free-form Python run.      A backend receives, Default, secure backend: the Rust ``open-edit-sandbox`` binary     (bwrap + secc (+26 more)

### Community 63 - "get_asset_or_error"
Cohesion: 0.09
Nodes (33): get_asset_or_error(), Exception, Base class for tool-domain errors surfaced as ``{"status": "error"}``., Tool error that should be retried later (e.g. transcription pending).      Norma, Look up an asset in the project's CAS.      Returns ``(asset, None)`` on success, Check an asset has word-level alignment.      Returns ``None`` when ``asset.alig, require_alignment(), ToolError (+25 more)

### Community 64 - "EffectCatalog"
Cohesion: 0.15
Nodes (17): EffectCatalog, EffectSpec, ParamSpec, BaseModel, Path, Load the effect catalog from a directory of YAML files., In-memory registry of effect specs loaded from YAML., catalog_dir() (+9 more)

### Community 65 - "compute_edit_graph_hash"
Cohesion: 0.13
Nodes (22): compute_edit_graph_hash(), Canonical hashing of an edit graph for timeline snapshot caching., Return a stable sha256 hex digest for a list of operations.      Accepts op obje, derive_or_load_timeline(), Timeline snapshot cache policy over an ``EditGraphStore``.  ``derive_or_load_tim, Return the Timeline for ``project``, using a cached snapshot when the     edit g, _make_store(), Regression tests for the edit-graph hash order-sensitivity bug (H1).  Before Tas (+14 more)

### Community 66 - "showToast"
Cohesion: 0.18
Nodes (24): addAssetToTimeline(), addNoteAtPlayhead(), clearAssetsList(), deleteEdit(), hideEditDetail(), _isPlayableRender(), isProxyStale(), loadProjectState() (+16 more)

### Community 67 - "test_serve_ws.py"
Cohesion: 0.09
Nodes (22): _mock_execute_tool(), _mock_stream_chat(), patched_ws(), Any, Tests for the WebSocket chat endpoint.  Uses FastAPI's ``TestClient.websocket_co, Server sends a `ready` event right after accepting the WS., A full agent turn streams text → tool_start → tool_result → text → done., Connecting to an unknown project sends an error and closes. (+14 more)

### Community 68 - "select_encoder"
Cohesion: 0.08
Nodes (42): EncoderBackend, apply_overrides(), apply_profile_vcodec(), detect_gpu_vcodec(), EncoderSpec, _ffmpeg(), ffmpeg_video_args(), _override_pairs() (+34 more)

### Community 69 - "motion_graphics/templates/__init__.py"
Cohesion: 0.11
Nodes (15): button_cta(), Button template: call-to-action text on a bright background, static., cost_warning(), Cost template: warning-style text on a dark background, mild pulse., hook_fade_text(), Hook template: fade-in text on a colored background.  The render sandbox (W2) ex, Motion graphics templates, one per narrative beat type., mechanism_diagram() (+7 more)

### Community 70 - "kernel/__init__.py"
Cohesion: 0.14
Nodes (21): Shared editing kernel — tool dispatch, render jobs, pillar schemas.  Used by the, _append_ir_op(), _apply_generated_ops(), dispatch_edit(), dispatch_generate(), dispatch_query(), Any, Path (+13 more)

### Community 71 - "TestAssetsAlignment"
Cohesion: 0.17
Nodes (4): patch, Phase 4.5 W1: Asset.alignment field + AssetStore integration., Unit tests for Asset alignment fields and AssetStore integration., TestAssetsAlignment

### Community 72 - "bindEvents"
Cohesion: 0.18
Nodes (19): bindEvents(), executeCmd(), filterCmdList(), handleCmdKeydown(), handleFiles(), openCmdPalette(), openNotesModal(), openSettingsModal() (+11 more)

### Community 73 - "_generate_waveform_inspection_image"
Cohesion: 0.11
Nodes (25): _generate_waveform_inspection_image(), _probe_streams(), Path, skipif, Unit tests for waveform cut inspection image generation (visual_verify.py).  The, When shutil.which('ffmpeg') returns None, return error status dict., Verify vstack command building, timing calculation, and filter structure., Local copy of the deleted ``visual_verify._probe_streams``. (+17 more)

### Community 74 - "chat.js"
Cohesion: 0.25
Nodes (18): appendErrorMessage(), appendRenderEvent(), appendSearchResults(), appendTextDelta(), appendToolCard(), appendUserMessage(), clearChatLog(), completeToolCard() (+10 more)

### Community 75 - "test_agent_loop_stability.py"
Cohesion: 0.14
Nodes (21): _db_path(), Return the edit_graph.db path for the given project directory.      Delegates to, _FakeState, _patch_common(), asyncio, Regression tests for the v1.9 agent-loop stability fixes.  Covers the root cause, The loop must NOT re-call stream_chat after tools complete (the old     bug: sec, The LLM retries the same failing call with identical args; after 3     attempts (+13 more)

### Community 76 - "package.json"
Cohesion: 0.10
Nodes (20): hyperframes, dependencies, react, react-dom, remotion, @remotion/cli, @remotion/renderer, description (+12 more)

### Community 77 - "tool_result"
Cohesion: 0.10
Nodes (40): F, Decorator: catch exceptions and return the canonical error dict.      ``ToolRetr, tool_result(), load_project(), make_ir(), Load a Project from the project directory.      For read-back operations. Raises, Create an IR instance backed by the project's EditGraphStore.      For mutating, Agent tool registry.  This package is the canonical registry of agent tools. It (+32 more)

### Community 78 - "test_mcp_server.py"
Cohesion: 0.07
Nodes (60): dispatch_mcp_tool(), mcp_tool_schemas(), Any, Path, Anthropic-shaped schemas for pillars + render helpers., Serialize a tool result for MCP TextContent., Execute one MCP tool against the pinned project.      Returns a JSON-serializabl, result_to_json() (+52 more)

### Community 79 - "make_error"
Cohesion: 0.18
Nodes (14): ErrorCodes, make_error(), Any, Exception, Unified error envelope for the Open Edit server.  Provides a single, dependency-, String constants for the unified error ``code`` field., Return a unified error envelope dict., Build an error envelope from an exception, stringifying its message. (+6 more)

### Community 80 - "transcribe"
Cohesion: 0.15
Nodes (12): _has_whisper(), Path, faster-whisper integration for word-level alignment.  Per phase4-design-revised., Resolve Whisper model size from arg or ``OPEN_EDIT_WHISPER_MODEL``., Resolve language override from arg or ``OPEN_EDIT_WHISPER_LANGUAGE``.      Empty, Transcribe an audio/video file to word-level alignment.      ``model_size`` defa, transcribe(), whisper_language() (+4 more)

### Community 81 - "test_serve_cost_badge.py"
Cohesion: 0.10
Nodes (19): Tests for the cost badge in the chat UI (v1.4 P1-3).  The cost badge sits next t, Source=pi: render the per-turn + session cost in dollars., Source=computed (anthropic/openai): same dollar-format label     as pi. The sour, Source=unavailable: show the honest "cost n/a" message     instead of a fake $0., The cost badge factory is intentionally focused: it only     reacts to ``cost_up, The chat log's ``handleWsEvent`` must route ``cost_update``     events to the co, When source=pi or source=computed, the badge text contains     a $ glyph. Pinned, Until the first ``cost_update`` event arrives, the badge     should be hidden. T (+11 more)

### Community 82 - "bridge.py"
Cohesion: 0.11
Nodes (26): Exception, Exception types and result types for the free-form Python sandbox., Result of a render-sandbox run (Phase 4.5 W2).      Distinct from open_edit.rend, Raised for unrecoverable preflight/setup errors. NOT for runtime failures     (t, RenderResult, SandboxError, lib_version_supported(), _load_manifest() (+18 more)

### Community 83 - "run_render"
Cohesion: 0.08
Nodes (27): Path, P9: resolve a caller-supplied workdir.      The AI may operate on any directory;, Run a render and always return a structured result., Run heavy-compute code in the render sandbox. Returns a RenderResult     (never, Return a bounded, single-line detail safe to show to an agent.      Backend deta, run_render(), _run_render_impl(), _sanitize_agent_detail() (+19 more)

### Community 84 - "list_assets"
Cohesion: 0.27
Nodes (10): _is_derivative(), list_assets(), Any, pyagent_list_assets: list all ingested assets in the project.  Exported as ``lis, Return ingested assets for the project.      By default **excludes** Remotion re, Tests for the list_assets tool (Wave 1.2)., test_list_assets_no_assets_dir_is_empty(), test_list_assets_returns_empty_for_empty_project() (+2 more)

### Community 85 - "ProjectPaths"
Cohesion: 0.08
Nodes (20): Any, Adapts an EditGraphStore to the IR's SupportsAppend protocol.      EditGraphStor, _StoreBuffer, pyagent_run_python: invokes the Phase 3 free-form Python sandbox.  Per phase4-de, ProjectPaths, Path, Single source of truth for the on-disk project layout.  Canonical server layout, Resolved paths for one Open Edit project directory.      ``root`` is the project (+12 more)

### Community 86 - "compress_silence"
Cohesion: 0.13
Nodes (25): probe_duration(), Path, Return the container duration of ``path`` in seconds., build_keep_ranges(), compress_silence(), compress_silence_audio(), _concat_ranges(), extract_audio() (+17 more)

### Community 87 - "_build_system_prompt"
Cohesion: 0.23
Nodes (12): _build_state_summary(), _build_system_prompt(), System prompt construction (DETERMINISTIC — see hard requirement #5)., Return a brief summary of the project state (under 1KB)., Build the system prompt.      Deterministic: the same ``state`` always produces, FakeProjectState, Minimal stand-in for projects_mod.ProjectState., test_build_state_summary_under_1kb() (+4 more)

### Community 88 - "test_opencode_adapter.py"
Cohesion: 0.18
Nodes (19): _map_stop_reason(), normalize_opencode_line(), parse_opencode_events(), Any, v1.7 — opencode CLI event normalizer.  Reads a sequence of bytes from an ``openc, Read raw stdout lines from ``opencode run --format json`` and yield     ``Stream, Map opencode's ``part.tokens`` + ``part.cost`` to our usage shape., Map one raw stdout line to 0..n ``StreamEvent``-shaped dicts.      Blank / non-J (+11 more)

### Community 89 - "ensure_schema"
Cohesion: 0.11
Nodes (23): Path, current_version(), ensure_schema(), _migration_files(), Connection, Path, Lightweight, safe SQLite migration runner for the edit-graph store.  Schema evol, Return the schema version recorded in ``PRAGMA user_version``. (+15 more)

### Community 90 - "test_transcription_pack.py"
Cohesion: 0.16
Nodes (17): get_transcript_packed(), Any, Path, Return packed transcript string for target asset.      Args:         args: {"ass, format_timestamp(), pack_transcript(), Format word alignments into silence-aware, speaker-grouped Markdown string., Format seconds into timestamp string MM:SS.ms (or HH:MM:SS.ms if >= 1hr). (+9 more)

### Community 91 - "remotion_bridge.mjs"
Cohesion: 0.11
Nodes (15): absEntry, absOut, absRoot, compositionId, concurrency, extraArgs, imageFormat, output (+7 more)

### Community 92 - "test_serve_render_jobs.py"
Cohesion: 0.11
Nodes (21): BaseModel, RenderRequest, projects_root_tmp(), asyncio, Tests for the durable render-job lifecycle (v1.7+).  Background: the legacy in-m, Non-``proxy|final|overlay`` modes are rejected with 400 before     anything is e, Every enqueued job carries a ``created_at`` timestamp (float)., A job transitions queued → running → succeeded and records the     render output (+13 more)

### Community 93 - "pyagent_search_assets.py"
Cohesion: 0.12
Nodes (31): _cache_get(), _cache_put(), _endpoint_for_error(), _freesound_attribution_required(), _freesound_attribution_text(), _http_get_json(), _is_cc0_license(), _is_plain_by_license() (+23 more)

### Community 94 - "visual_verify.py"
Cohesion: 0.17
Nodes (20): _is_summary(), prune_images(), v1.5 visual verification module.  Pure (or near-pure) functions for the post-ren, Return a copy of ``result`` with ``verification.frames`` removed.      Frame dat, Return a new slim view of ``history`` with image blocks stripped and     verific, _strip_verification_frames(), _make_tool_result_message(), _make_verification_result() (+12 more)

### Community 95 - "test_ir_api.py"
Cohesion: 0.10
Nodes (8): ir_instance(), Phase 3 Task 4: IR API real implementation (12 methods, parent_id stamped)., H10: the buffer is a SupportsAppend; works with any list-like., Schema errors fail at build time (Pydantic ValidationError)., IR.add_effect must return the op's effect_id, distinct from edit_id.      Regres, test_add_effect_returns_canonical_effect_id(), test_ir_works_with_list_subclass(), test_pydantic_validation_error_on_bad_input()

### Community 96 - "test_serve_verify_chip.py"
Cohesion: 0.16
Nodes (17): v1.5: tests for the verification chip in the chat UI.  A small chip near the cha, On a ``verification_started`` event the chip should drop the     ``hidden`` clas, ``outcome=pass`` is the happy path: chip transitions to     ``verified`` (green), ``outcome=uncertain`` and ``outcome=failed`` both mean the visual     check didn, ``outcome=skipped`` is the path where the server itself decided     not to run v, ``outcome=capped`` is the path where the per-turn render cap     was hit. The ch, After a turn finishes, the chip must reset to ``idle`` and     re-hide. Per the, Run ``script_body`` (JS) through the harness and return the     ``(returncode, s (+9 more)

### Community 97 - "generate_visual"
Cohesion: 0.15
Nodes (17): generate_visual(), MotionTemplateParams, BaseModel, Path, Motion graphics engine: runs templates to produce video assets.  Per phase4-desi, Parameters consumed by every motion-graphics template.      ``asset_references``, Run a motion-graphics template, ingest the output, emit AddClipOp.      Args:, Phase 4.5 W7: motion graphics templated skill. (+9 more)

### Community 98 - "materialize.py"
Cohesion: 0.09
Nodes (43): _materialize_key(), materialize_remotion_compositions(), Path, Materialize Remotion compositions into CAS clips before MLT emit.  Fails hard on, Render pending Remotion compositions and inject clips onto tracks.      Mutates, _render_cache(), Remotion composition renderer for Open Edit.  Materializes React Remotion compos, _alpha_vcodec() (+35 more)

### Community 99 - "now_iso8601"
Cohesion: 0.11
Nodes (14): now_iso8601(), Return the current UTC time as an ISO 8601 string., Record a command for idempotency. No-op if command_id exists., JobLock, Path, In-flight job lock backed by the SQLite jobs table.  A single lock for all kinds, Single-slot lock for sandbox runs, renders, and migrations., Release locks older than STALE_LOCK_TIMEOUT_SEC. (+6 more)

### Community 100 - "_node_harness.py"
Cohesion: 0.19
Nodes (12): app_js_path(), harness(), Path, Shared harness for the v1.4 Node-sandbox frontend tests.  The frontend (``open_e, Build a Node script that loads app.js as an ES module into a     stubbed browser, Write ``script`` to a temp file and run it with Node. The script     receives th, Absolute path to the app entry-point ES module.      Flat layout: ``tests/`` sit, run_node_script() (+4 more)

### Community 101 - "orchestrator.py"
Cohesion: 0.09
Nodes (33): _fail(), _gpu_decode_available(), BaseModel, Path, Render orchestrator: plan → cache → emit → frame-server pipe → snapshot → result, Render a project to an MP4.      project_dir: directory containing `.open_edit/e, Single failure path: produce the failure RenderResult.      When ``record_failed, Outcome of a render operation. (+25 more)

### Community 102 - "melt_runner.py"
Cohesion: 0.19
Nodes (24): MeltTimeoutError, PipeResult, PipeRunError, Exception, RuntimeError, Melt subprocess execution: command building, timeout, and cache mediation., Run melt (video -> raw pipe) and ffmpeg concurrently; audio pass first.      std, Raised when melt exceeds its wall-clock budget. (+16 more)

### Community 103 - "test_serve_cost.py"
Cohesion: 0.04
Nodes (69): _accumulate_session_usage(), compute_anthropic_cost(), compute_openai_cost(), default_pi_sessions_dir(), encoded_cwd_segment(), find_pi_session_file(), _iter_files(), load_pricing() (+61 more)

### Community 104 - "test_review_ui.py"
Cohesion: 0.18
Nodes (16): auto_proxy_enabled(), is_review_only(), Review-only server mode (no built-in LLM / chat)., When set, the review UI may enqueue a proxy render after graph changes., True when the UI is a harness-driven review studio (MCP plugin workflow)., get_ui_config(), Any, Frontend mode flags (review studio vs full agent UI). (+8 more)

### Community 105 - "AddClipOp"
Cohesion: 0.04
Nodes (19): AddClipOp, AddTransitionOp, Pytest configuration for open_edit tests., A project with one asset pre-ingested, suitable for free-form runs (L9).      Se, tmp_project_with_assets(), Path, End-to-end render test: ingest -> ops -> melt -> QC -> cache.  Ingest 3 fixture, Render with a scale override; verify the output resolution via ffprobe. (+11 more)

### Community 106 - "profiles.py"
Cohesion: 0.14
Nodes (22): _mode_default_quality(), profile_fingerprint(), profile_to_mlt_args(), profile_with_quality(), Render profile selection and MLT consumer arg generation., Resolve a profile name + mode into a RenderProfile carrying quality.      Defaul, The EncoderSpec for a profile: tier (profile.quality) + raw overrides., Stable cache-key component: resolution + quality + overrides + backend. (+14 more)

### Community 107 - "_SlowPopen"
Cohesion: 0.20
Nodes (6): Fake Popen that stays alive until kill() is called., Cancellation during the render calls kill() and raises OverlayRenderError., Cancellation during ffmpeg calls kill() and raises OverlayRenderError., _SlowPopen, test_composite_with_background_cancellation_kills_subprocess(), test_render_overlay_layer_cancellation_kills_subprocess()

### Community 108 - "AssetStore"
Cohesion: 0.13
Nodes (10): AssetStore, Content-addressed media asset store., skipUnless, T1: Conftest fixture sanity check.  The fixture must produce on-disk state that, Fixture writes CAS asset + sidecar + edit_graph entry to disk., test_fixture_persists_on_disk_state(), End-to-end (no mocks): the dev backend actually runs the generated     bootstrap, test_dev_backend_executes_real_python() (+2 more)

### Community 109 - "serve/agent/__init__.py"
Cohesion: 0.11
Nodes (39): Any, Path, CLI-owned turns (pi / opencode / antigravity / jcode).  CLI providers run a COMP, Run one turn against a provider that owns its agent loop., _run_cli_owned_turn(), accumulate_usage(), _cost_sidecar_path(), _create_bg_task() (+31 more)

### Community 110 - "history_store.py"
Cohesion: 0.16
Nodes (22): append_to_conversation(), _compact_jsonl(), _conversations_dir(), load_conversation(), new_conversation_id(), Any, Path, Conversation persistence for the agent loop.  The conversation history is persis (+14 more)

### Community 111 - "cap_tool_result"
Cohesion: 0.20
Nodes (15): cap_tool_result(), Any, Cap oversized tool results before they enter conversation history.  Called from, Return a copy of ``result`` with oversized fields truncated.      * Truncates ``, Tests for the result_capper module., test_custom_max_chars_honored(), test_error_field_truncated(), test_field_under_custom_max_chars_untouched() (+7 more)

### Community 112 - "boot"
Cohesion: 0.23
Nodes (13): boot(), refreshProjects(), renderProjectSelect(), selectProject(), createChatStatus(), createCostBadge(), createVerifyChip(), connectWS() (+5 more)

### Community 113 - "test_phase567_edit_render.py"
Cohesion: 0.12
Nodes (18): apply_command(), open_store(), Any, Path, Append one validated timeline command and return the new revision., ValueError, Durable render scheduling and subprocess lifecycle management.  The service is d, Raised when a render cannot be accepted (invalid/stale graph). (+10 more)

### Community 114 - "test_cli.py"
Cohesion: 0.21
Nodes (13): CompletedProcess, Path, End-to-end CLI tests for open_edit init/list/summary/undo., `open_edit render` runs without error on an empty project (early return)., `--version` reports the version from package metadata, not a     hard-coded stri, Regression: `open_edit notes` (no subcommand) used to crash with     NameError b, _run(), test_init_ingests_videos() (+5 more)

### Community 115 - "test_serve_llm_config_api.py"
Cohesion: 0.29
Nodes (11): client_and_project(), MonkeyPatch, Path, TestClient, Tests for the GET/PUT /api/projects/{id}/llm-config REST routes., Antigravity is a valid provider — the adapter is registered., test_get_llm_config_returns_current_config(), test_put_llm_config_antigravity_is_now_valid() (+3 more)

### Community 116 - "Asset"
Cohesion: 0.06
Nodes (58): Asset, asset_stream_url(), _asset_to_info(), AssetInfo, EffectInfo, get_project_state(), _initialise_project(), _is_complete_render_mp4() (+50 more)

### Community 117 - "test_serve_chat_status.py"
Cohesion: 0.17
Nodes (11): Tests for the frontend chat-status indicator (v1.4 P1-2).  The chat-status indic, The user-visible label for ``tool_running`` must include the tool     name (e.g., Per the brief, the indicator "clears within one frame of ``DONE``     or ``error, A second ``send()`` while the indicator is still showing the     previous turn m, ``window.OpenEdit.__testHooks.createChatStatus`` must exist so     tests can dri, A complete turn walks the indicator through every state and ends     back at idl, test_chat_status_error_then_done_clears(), test_chat_status_full_turn_lifecycle() (+3 more)

### Community 118 - "test_serve_search_assets.py"
Cohesion: 0.17
Nodes (11): Frontend tests for the v1.4 P1-1 search-assets results panel.  When the assistan, ``window.OpenEdit.__testHooks.appendSearchResults`` must exist so     tests can, The panel must produce one card per result, with the license     badge and "Add, Each card must surface the license string verbatim so the user     knows the ter, When the tool returns ``{error: "..."}``, the panel must show     the error (not, Clicking the "Add to project" button must trigger an     ``import_asset`` chat m, test_append_search_results_add_button_fires_import(), test_append_search_results_is_exposed_on_test_hooks() (+3 more)

### Community 119 - "staging.py"
Cohesion: 0.16
Nodes (16): list, Internal: a single op in ops.jsonl failed referential or schema validation., _ValidationError, _assets_dir_for_workdir(), _FlushingBuffer, _load_assets_via_store(), _load_project_for_validation(), Path (+8 more)

### Community 120 - "ops.py"
Cohesion: 0.16
Nodes (18): delete, delete_op(), post_timeline_command(), BaseModel, JSONResponse, patch, post, Edit-graph (ops) routes: timeline commands, op status, reorder, delete. (+10 more)

### Community 121 - "TokenAuthMiddleware"
Cohesion: 0.17
Nodes (15): _extract_token(), _is_localhost(), BaseHTTPMiddleware, Request, Response, Fail-safe bearer-token auth with a localhost bypass.      Auth is only enforced, TokenAuthMiddleware, _ok_call_next() (+7 more)

### Community 122 - "TestPhase1Integrity"
Cohesion: 0.19
Nodes (3): Connection, Tests for Phase 1 storage integrity features., TestPhase1Integrity

### Community 123 - "test_frozen_frames.py"
Cohesion: 0.11
Nodes (29): FrozenFramesResult, FrozenSpan, list_frozen_frames(), _parse_freezedetect(), BaseModel, Frozen-frame detection for QC.  Wraps ffmpeg's ``freezedetect`` filter. A segmen, Return frozen-frame spans for ``video_path`` (any span ≥ ``min_sec``)., Parse freezedetect lines from ffmpeg's stderr.      freezedetect emits a ``freez (+21 more)

### Community 124 - "run_trigger_render"
Cohesion: 0.13
Nodes (25): _build_render_spec(), _extract_output_path(), _load_timeline(), make_should_cancel(), _probe_duration(), Any, Path, Kernel-side overlay render trigger.  This module hosts the ``trigger_render`` to (+17 more)

### Community 125 - "Analysis Report: Automatic 30ms Audio Micro-Fades in MLT Emitter (Milestone 1 / R1)"
Cohesion: 0.10
Nodes (20): 1.1 Core Flow & Primary Functions, 1. MLT XML Emission Architecture in `emitter.py`, 2.1 Filter Emission (`_emit_filter`), 2.2 OpenEdit IR Catalog Spec for `volume`, 2. Filter Representation & Attachment in `open_edit`, 3.1 Objective & Rationale, 3.2 Frame Count & Keyframe Calculation, 3.3 Target XML Output Example (+12 more)

### Community 126 - "_coerce_event"
Cohesion: 0.25
Nodes (10): _coerce_event(), Any, Tests for the StreamEvent contract (Wave 3.3)., StreamEvent must be importable and annotated — not just a docstring., A provider emitting a new event type should not crash the agent loop., test_coerce_event_fills_missing_text_with_empty_string(), test_coerce_event_handles_unknown_type_gracefully(), test_coerce_event_passes_through_valid_text_delta() (+2 more)

### Community 127 - "extension.ts"
Cohesion: 0.20
Nodes (4): OPEN_EDIT_PKG, REAL_DIR, REAL_FILE, ToolDef

### Community 128 - "routers/projects.py"
Cohesion: 0.11
Nodes (26): BackgroundTasks, get_thumbnail(), post_create_project(), post_ingest(), post_project_note(), Any, JSONResponse, Path (+18 more)

### Community 129 - "Detailed Analysis: 30ms Audio Micro-Fades in MLT Emitter (Milestone 1 / R1)"
Cohesion: 0.10
Nodes (20): 1.1 Document Hierarchy & Entry Generation, 1.2 How Filters are Attached to Playlist Clip Entries, 1. Audio Properties & Filter Attachment Mechanism in `emitter.py`, 2.1 Standardized Filter Service in `open_edit`, 2.2 XML Keyframe Representation for Micro-Fades, 2.3 Cascading Multiplier Behavior with User Filters, 2. MLT Filter Names & Properties for Audio Volume Fades, 3.1 Timecode & Frame Calculation Rules in `emitter.py` (+12 more)

### Community 130 - "pi_extension/package.json"
Cohesion: 0.22
Nodes (8): description, main, name, private, scripts, check, type, version

### Community 131 - "edit_graph.py"
Cohesion: 0.11
Nodes (15): new_note_id(), new_version_id(), Shared id and timestamp generators.  Single source of truth for UUIDs and ISO-86, Return a fresh review-note id (``note_<hex12>``)., Return a fresh render-version id (``v_<hex12>``)., SQLite-backed command idempotency store.  Tracks tool commands keyed by command_, Shared SQLite connection helper for the storage layer.  All stores open the proj, SQLite-backed edit graph store.  One .db file per project. WAL mode for concurre (+7 more)

### Community 132 - "test_orchestrator_fails_hard_on_remotion_error"
Cohesion: 0.29
Nodes (8): MonkeyPatch, Path, skipif, Full proxy path: Remotion materialize then melt., Materialize failure must fail the render (no silent omission)., remotion_project(), test_orchestrator_fails_hard_on_remotion_error(), test_remotion_proxy_render_via_orchestrator()

### Community 133 - "routers/config.py"
Cohesion: 0.15
Nodes (25): HTTPException, _check_rate_limit(), get_llm_config(), get_provider_models(), get_settings_keys(), list_discovered_runtimes(), LLMConfigRequest, LLMConfigResponse (+17 more)

### Community 134 - "save_stored_key"
Cohesion: 0.16
Nodes (20): _ensure_keys_file_dir(), get_masked_keys_summary(), get_stored_key(), load_all_stored_keys(), mask_key(), Any, Path, v1.8 — Secure Non-Technical BYOK (Bring Your Own Key) Store.  Stores user-entere (+12 more)

### Community 135 - "tool_executor.py"
Cohesion: 0.16
Nodes (23): public_job(), Stable JSON-friendly job representation for REST and WebSocket callers., _cached_done_result(), _canonicalize_project_id(), execute_trigger_render(), _is_error_result(), _payload_hash(), Any (+15 more)

### Community 136 - "Milestone 3 Analysis Report: Dual-Panel Waveform Cut Inspection Image Generation"
Cohesion: 0.10
Nodes (19): 1. Executive Summary, 2.1 Inventory of `open_edit/serve/visual_verify.py`, 2.2 Usage in `open_edit/serve/agent.py`, 2. Codebase Baseline & Function Inventory, 3.1 Concept & Layout Strategy, 3.2 Composite Layout Modes, 3. Architecture Design: Dual-Panel Waveform Composite Image Generation, 4.1 Standard Case: Video + Audio (`has_video=True`, `has_audio=True`) (+11 more)

### Community 137 - "Milestone 3 Analysis Report: Waveform Cut Inspection Image Generation"
Cohesion: 0.11
Nodes (17): 1. Executive Summary, 2. Codebase Baseline Observation, 3.1 Corner Case 1: Audio-Only Inputs (MP3, WAV, AAC, or MP4 without video stream), 3.2 Corner Case 2: Video-Only Inputs (Silent video clips without audio track), 3.3 Corner Case 3: Short Clip Windows & Boundary Timestamps, 3.4 Corner Case 4: Missing FFmpeg Binary, 3.5 Corner Case 5: Error Handling & Subprocess Failures, 3. Comprehensive Corner Case Analysis (+9 more)

### Community 138 - "run_qc_gate"
Cohesion: 0.16
Nodes (18): BaseModel, Path, QCCheck, QCReport, QC gate — runs all 10 checks and aggregates the results.  Implements the check s, Run all QC checks against a rendered video file.      Parameters     ----------, run_qc_gate(), Tests for the QC gate (documented 6 checks + pipeline diagnostics). (+10 more)

### Community 139 - "test_serve_loading_state.py"
Cohesion: 0.25
Nodes (7): Tests for the v1.4 P2 loading state on the asset list.  The brief: "Asset list a, While ``api.getProjectState`` is in flight, the assets list     must show a load, When ``getProjectState`` fails, the assets list should not be     stuck on a loa, When the user switches projects, the assets list must NOT     keep showing the o, test_load_project_state_clears_loading_marker_on_error(), test_load_project_state_shows_loading_marker_during_fetch(), test_project_switch_shows_loading_state_not_stale_data()

### Community 140 - "Open Edit as a local MCP server"
Cohesion: 0.11
Nodes (19): Agent skills (all harnesses), Arabic transcription, Cursor config, How hosts load them, Initialize a project, Install, License, Linux / macOS (+11 more)

### Community 141 - "serve/__init__.py"
Cohesion: 0.21
Nodes (10): _build_verification_result(), _maybe_verify_render(), Any, Path, Visual verification helpers (v1.5)., Map a render error string to a ``verdict_source`` value., Build a single ``verification_result`` AgentEvent., Run the verification stage for one ``trigger_render`` result.      Returns ``(ev (+2 more)

### Community 142 - "test_agent_tool_table_coverage.py"
Cohesion: 0.19
Nodes (15): _cache_clear(), _asset(), _configure_style_profile(), _graph(), MonkeyPatch, parametrize, Path, SimpleNamespace (+7 more)

### Community 143 - "Install Open Edit"
Cohesion: 0.11
Nodes (18): 1. Clone, 2. Install the Python package (MCP), 3. Create an edit project, 4. Configure Cursor MCP, 5. Optional: review UI, 6. Smoke check, Install Open Edit, Linux / macOS (+10 more)

### Community 144 - "test_sandbox_observations.py"
Cohesion: 0.29
Nodes (3): Verify the strace observation fixtures are present and parseable.  The strace fi, Each strace file should list at least 5 distinct syscalls., test_strace_files_contain_real_syscalls()

### Community 145 - "Handoff Report — Reviewer 1 for Milestone 1 (30ms Audio Micro-Fades)"
Cohesion: 0.12
Nodes (16): 1. Observation, 2. Logic Chain, 3. Caveats, 4. Conclusion, 5. Verification Method, Actionable Fix Suggestions for Worker 1:, [Critical] Finding 1: INTEGRITY VIOLATION — Facade Test Assertion Self-Certifying Muted Short Clips, Findings (+8 more)

### Community 146 - "analyze"
Cohesion: 0.17
Nodes (14): analyze(), _analyze_rule_based(), _analyze_with_llm(), Narrative analyzer skill: classify transcript segments into beat types.  Per pha, Analyze the asset's transcript and return narrative segments.      With use_llm=, Segment aligned words at sentence-like boundaries., LLM-backed beat classification.      NOT IMPLEMENTED. Warns and returns the rule, Phase 4.5 W4: narrative analyzer skill. (+6 more)

### Community 147 - "Deep-Dive Technical Analysis: 30ms Audio Micro-Fades in MLT Emitter"
Cohesion: 0.12
Nodes (15): 1. Corner Cases for 30ms Audio Micro-Fades, 2. Pytest Environment, Test Structure & Helper Dependencies, 3. Edge Cases & Potential Regression Risks in `emitter.py`, 4. Exact Implementation Recommendations, 5. Recommended Unit Tests (`tests/test_render/test_emitter.py`), A. Clips Shorter than 60ms (< 60ms, down to 1 frame / 0s), A. EmitterConfig Extension (`open_edit/render/emitter.py`), A. Test Execution & Location (+7 more)

### Community 148 - "Milestone 2 (R2): Token-Efficient Phrase-Packed Transcript Tool Analysis"
Cohesion: 0.12
Nodes (15): 1. Architectural Overview & Context, 2.1 Storage & IR Layer (`open_edit/storage/transcription.py` & `open_edit/ir/types.py`), 2.2 Agent Tools Layer (`open_edit/agent/tools/`), 2.3 Pillar Tools & Schema Registration (`open_edit/serve/`), 2. Codebase Investigation Findings, 3.1 Data Flow & Algorithm Steps, 3.2 Detailed Formatting Rules, 3. Phrase Packing Algorithm Specification (+7 more)

### Community 149 - "3. Confirmed and High-Risk Findings"
Cohesion: 0.12
Nodes (16): 3. Confirmed and High-Risk Findings, OE-P0-001 — Provider Registry Drift, OE-P0-002 — CLI Agent Ownership Does Not Match Tool Capability, OE-P0-003 — Upload Contract Is Broken for Multiple Files, OE-P0-004 — WebSocket Authentication and Origin Protection Must Be Explicit, OE-P1-005 — Saving LLM Configuration Deletes Other TOML Sections, OE-P1-006 — Provider API-Key Selection Can Use the Wrong Credential, OE-P1-007 — CLI Conversation Context Is Lost (+8 more)

### Community 151 - "test_serve_module_structure.py"
Cohesion: 0.33
Nodes (5): Test the v1.4 P2 ES module structure is intact.  The brief: "Add a Node-sandbox, The entry point imports from each sibling module (state,     dom, api, assets, c, The entry-point ES module loads cleanly and exposes the     full ``__testHooks``, test_module_dependencies_resolve(), test_module_loads_and_exposes_test_hooks()

### Community 152 - "list_black_frames"
Cohesion: 0.20
Nodes (13): BlackFramesResult, BlackSpan, list_black_frames(), _parse_blackdetect(), BaseModel, Black-frame detection for QC.  Wraps ffmpeg's blackdetect filter. A frame is "bl, Return black-frame spans for the [in_sec, out_sec] range., Parse blackdetect lines from ffmpeg's stderr. (+5 more)

### Community 153 - "test_huge_line_stream_no_limit_overrun"
Cohesion: 0.67
Nodes (3): asyncio, Verify that a single JSON line > 2MB does not raise LimitOverrunError., test_huge_line_stream_no_limit_overrun()

### Community 154 - "test_timeline_full.py"
Cohesion: 0.50
Nodes (3): Test that GET /api/projects/{id} includes timeline_full., An existing project should return timeline_full with tracks/clips., test_project_state_includes_timeline_full()

### Community 155 - "get_profile_path"
Cohesion: 0.28
Nodes (13): _chmod(), _default_profile(), get_config_dir(), get_profile_path(), get_user_project_meta(), Path, Manages ~/.open-edit/ directory and config files., Return user-level (file-based) per-project metadata. Creates the file on first a (+5 more)

### Community 156 - "Checks (and what to do about a failure)"
Cohesion: 0.13
Nodes (14): Asset-reference failures at append, `audio_sync`, `black_frames`, Checks (and what to do about a failure), `duration`, `frozen_frames`, Over-aggressive cut density, `overlays_burned` (+6 more)

### Community 157 - "Render Pipeline Fix — Design (2026-08-01)"
Cohesion: 0.13
Nodes (14): Architecture, Cache key, Components, Error handling, Future (explicitly deferred), Goals, Hardware decode, New pipeline (all projects) (+6 more)

### Community 158 - "diagnostics"
Cohesion: 0.15
Nodes (15): exception_handler, diagnostics(), get_health(), health(), _http_exception_handler(), Any, Exception, get (+7 more)

### Community 163 - "Rules"
Cohesion: 0.13
Nodes (14): Color, audio, overlays — the free-form escape hatch, Cut dead air on sense boundaries, not raw gaps, Edit planning, Input, Match the target duration, Output, Pacing, Rules (+6 more)

### Community 166 - "Open Edit MCP — agent playbook"
Cohesion: 0.14
Nodes (14): Common recipes, Cut silence, `edit_project` generate (proposals — review then apply), `edit_project` operations (immediate), Hard rules (token savers), Ingest + put clips on timeline, Open Edit MCP — agent playbook, Priority order (+6 more)

### Community 168 - "open_conn"
Cohesion: 0.06
Nodes (27): CommandStore, Path, SQLite store for command idempotency records., Return True if a command with the given id has been recorded., Mark a command as finished with a status and optional result., Return the stored result_json for a command, or None., Return the stored status for a command, or None., open_conn() (+19 more)

### Community 169 - "get_thumbnail"
Cohesion: 0.23
Nodes (12): get_thumbnail(), _long_edge_scale(), _probe_dimensions(), BaseModel, Single-frame thumbnail extraction for QC., Return (width, height) via ffprobe. Returns (0, 0) on failure., Extract a single JPEG frame at `timestamp_sec`., ThumbnailResult (+4 more)

### Community 170 - "get_visual_verify_config"
Cohesion: 0.24
Nodes (12): _env_bool(), _env_int(), _env_str(), get_overlay_config(), Any, Render-side env config shared by the kernel overlay trigger and serve.  Homes fo, Return the typed config for the v1.6 HTML overlay pipeline., get_visual_verify_config() (+4 more)

### Community 171 - "Open Edit MCP — agent playbook"
Cohesion: 0.14
Nodes (14): Common recipes, Cut silence, `edit_project` generate (proposals — review then apply), `edit_project` operations (immediate), Hard rules (token savers), Ingest + put clips on timeline, Open Edit MCP — agent playbook, Priority order (+6 more)

### Community 172 - "Phase 6 — Deduplicate Shared Infrastructure"
Cohesion: 0.15
Nodes (13): Phase 6 — Deduplicate Shared Infrastructure, Task 6.10: Derive provider metadata from the registry, Task 6.11: Extract cost-aggregation helpers in the agent loop, Task 6.12: Collapse result capping into one implementation, Task 6.1: Create `ir/ids.py` and migrate 22 call sites, Task 6.2: Create `storage/db.py` shared connection helper, Task 6.3: Consolidate schema DDL into migrations, Task 6.4: Single project-path resolution (`ProjectPaths`) (+5 more)

### Community 177 - "probe_streams"
Cohesion: 0.24
Nodes (11): _as_float(), probe_streams(), BaseModel, Stream-level probing for QC (streams / duration / audio_sync checks).  Single ff, Return stream counts + durations for ``video_path`` via one ffprobe call., StreamsInfo, Tests for stream-level QC probing., The testdata clips are 2s video-only MP4s. (+3 more)

### Community 184 - "Rules"
Cohesion: 0.14
Nodes (14): Color, audio, overlays — the free-form escape hatch, Cut dead air on sense boundaries, not raw gaps, Edit planning, Input, Match the target duration, Output, Pacing, Rules (+6 more)

### Community 185 - "Phase 1 — Delete Dead Code"
Cohesion: 0.17
Nodes (12): Phase 1 — Delete Dead Code, Task 1.10: Delete `_ReadBackBuffer`, stale docstrings, orphaned skill, Task 1.11: Fix `cli.py` version string, Task 1.1: Delete `serve/_cli_patch.py`, Task 1.2: Delete the three serve shims, Task 1.3: Migrate pydantic_compat users and delete the shim, Task 1.4: Delete the legacy render-job registry in app.py, Task 1.5: Delete `ir/commutativity.py` (+4 more)

### Community 186 - "build_prior_state"
Cohesion: 0.20
Nodes (13): build_prior_state(), _format_slice(), _load_profile(), Builds the prior_state block for the system prompt.  Per phase4-design-revised.m, _notes_db_path(), Return the notes.db path. Notes live at the project ROOT     (``<root>/notes.db`, test_notes_db_path_is_project_root(), Phase 4 Task 3: prior_state block builder. (+5 more)

### Community 187 - "test_layering.py"
Cohesion: 0.29
Nodes (10): _imports_module(), _offenders(), _py_files(), Path, Layering guard tests.  Enforce the hard dependency rules: - kernel must never im, True if src contains an import statement for ``module`` (exact dotted-path compo, test_ir_never_imports_upper_layers(), test_kernel_never_imports_serve() (+2 more)

### Community 189 - "Target System Architecture"
Cohesion: 0.14
Nodes (13): Agent Tool Protocol, Architecture, Canonical Project Layout, Decision, Event Protocol (Normalized), Experimental limits (honest), Immutable Principles, Motion Graphics Backends (+5 more)

### Community 190 - "harness_skills/README.md"
Cohesion: 0.22
Nodes (5): How hosts should load them, Not agent skills, Open Edit harness skills, Planning & QC, Start here

### Community 191 - "Analysis Report: Token-Efficient Phrase-Packed Transcript Tool (Milestone 2 / R2)"
Cohesion: 0.14
Nodes (13): 1. Executive Summary, 2.1 Storage & Transcription Models, 2. Existing Data Structures & Architecture Analysis, 3.1 Phrase Packing Algorithm, 3.2 Timestamp Formatting, 3.3 Output Markdown Format, 3.4 Edge Case Handling, 3. Data Format Specification for `takes_packed.md` (+5 more)

### Community 192 - "Phase 5 — Split God Files"
Cohesion: 0.22
Nodes (9): Phase 5 — Split God Files, Task 5.1: Split `serve/agent.py` into `serve/agent/` package, Task 5.2: Split `serve/app.py` into routers, Task 5.3: Split `serve/llm.py` into `serve/llm/` package, Task 5.4: Split `sandbox_bridge.py` into `agent/sandbox/`, Task 5.5: Split `ir/apply.py`, Task 5.6: Split `storage/edit_graph.py`, Task 5.7: Split `render/orchestrator.py` (+1 more)

### Community 193 - "Tool-surface reference — the 4-pillar tools"
Cohesion: 0.22
Nodes (9): 1. `query_project` (read-only), 2. `edit_project` (mutations + creative generation), 3. `run_script` (free-form Python), 4. `trigger_render`, Authoritative source, Common mistakes (do not repeat these), Priority order (always follow this), Relevant source (read these in the real codebase) (+1 more)

### Community 194 - "Handoff Report — Milestone 3 (R3: Waveform Cut Inspection Image Generation)"
Cohesion: 0.14
Nodes (13): 1. Observation, 2. Logic Chain, 3. Caveats, 4. Conclusion, 5. Verification Method, Coverage Gaps, Handoff Report — Milestone 3 (R3: Waveform Cut Inspection Image Generation), Implementation Inspection (`open_edit/serve/visual_verify.py`) (+5 more)

### Community 195 - "2. Specific points the graph surfaced (concrete, file-level)"
Cohesion: 0.14
Nodes (13): 1. What OpenEdit actually is, 2.1 The `kernel/` migration is real but incomplete — finish it, then delete the shims, 2.2 Two divergent implementations of the same skill — one orphaned, one live and weaker, 2.3 JCode is still half-registered (unresolved since the last stabilization pass), 2.4 MCP server is correctly wired, not dead code, 2.5 Render pipeline is fully wired, multi-backend, and is the most complex single subsystem, 2.6 The old `OpenEdit_Repair_Plan.md` is ~70% executed — don't re-run it blind, 2. Specific points the graph surfaced (concrete, file-level) (+5 more)

### Community 196 - "set_pinned"
Cohesion: 0.39
Nodes (8): set_pinned(), _load_profile(), Phase 4 Task 3: style memory aggregation (pinned overrides)., Per spec section 8.6.7: keep last 3 versions as .bak., test_chmod_600(), test_keeps_last_3_backup_versions(), test_set_pinned(), test_set_pinned_accumulates()

### Community 197 - "Tool-surface reference — the 4-pillar tools"
Cohesion: 0.22
Nodes (9): 1. `query_project` (read-only), 2. `edit_project` (mutations + creative generation), 3. `run_script` (free-form Python), 4. `trigger_render`, Authoritative source, Common mistakes (do not repeat these), Priority order (always follow this), Relevant source (read these in the real codebase) (+1 more)

### Community 198 - "Real-world failure modes (watch for these)"
Cohesion: 0.25
Nodes (7): Asset-reference failures at append, Over-aggressive cut density, QC standards, Re-running after a failure, Real-world failure modes (watch for these), Stale server code, Untranscribed assets

### Community 199 - "Free-form ops & effect catalog — reference"
Cohesion: 0.25
Nodes (7): Free-form ops & effect catalog — reference, Free-form ops (escape hatch), Relevant source (read these in the real codebase), Structured effect catalog, Validation gap — read this before using free-form, What you CANNOT do, When to escape to free-form

### Community 200 - "capture_hint"
Cohesion: 0.24
Nodes (11): capture_style_hint(), pyagent_capture_style_hint: persist a confirmed user style preference., Store a confirmed style hint (and optional pin) in the global profile.      ``pr, capture_hint(), _load_profile(), Any, Persist a confirmed style hint with provenance.      Also pins ``key=value`` whe, _touch_meta() (+3 more)

### Community 201 - "5. Execution Phases"
Cohesion: 0.15
Nodes (13): 5. Execution Phases, Done when, Done when, Done when, Phase 5 — Make the Edit Graph a Correct Interactive Editor, Phase 6 — Consolidate and Harden Rendering, Phase 7 — Repair Frontend State and User Feedback, Phase 9 — Observability, Security, and Recovery (+5 more)

### Community 202 - "Phase 4 (cont.) — Tool Contract"
Cohesion: 0.29
Nodes (7): Phase 4 (cont.) — Tool Contract, Task 4.1: Create the tool contract module, Task 4.2: Migrate the 12 simple tools to `@tool_result`, Task 4.3: Migrate asset-fetch boilerplate, Task 4.4: Migrate timeline_ops and remotion tools to canonical shapes, Task 4.5: Standardize parameter aliases, Task 4.6: Replace getattr dispatch with an explicit TOOL_TABLE

### Community 203 - "Free-form ops & effect catalog — reference"
Cohesion: 0.29
Nodes (7): Free-form ops & effect catalog — reference, Free-form ops (escape hatch), Relevant source (read these in the real codebase), Structured effect catalog, Validation gap — read this before using free-form, What you CANNOT do, When to escape to free-form

### Community 204 - "Open Edit MCP reference"
Cohesion: 0.25
Nodes (7): Authoritative code (debug Open Edit only), Dual process (MCP + review UI), Env knobs (config, not code), Example tool arguments, IR op kinds (high level), Open Edit MCP reference, When to use `run_script`

### Community 205 - "Checks (and what to do about a failure)"
Cohesion: 0.29
Nodes (7): `audio_sync`, `black_frames`, Checks (and what to do about a failure), `duration`, `frozen_frames`, `overlays_burned`, `streams`

### Community 206 - "Remotion motion graphics in Open Edit"
Cohesion: 0.33
Nodes (6): Agent workflow, License, Props example, Remotion motion graphics in Open Edit, Security, When to use which backend

### Community 207 - "Open Edit MCP reference"
Cohesion: 0.29
Nodes (7): Authoritative code (debug Open Edit only), Dual process (MCP + review UI), Env knobs (config, not code), Example tool arguments, IR op kinds (high level), Open Edit MCP reference, When to use `run_script`

### Community 208 - "OpenEdit Code Restructure Implementation Plan"
Cohesion: 0.33
Nodes (5): Global Constraints, OpenEdit Code Restructure Implementation Plan, Phase 4 — Standardize the Tool Contract, Post-Plan Note, Task 4.0: Fix agent-loop project_id injection conflict + helper dispatch

### Community 209 - "Phase 2 — Fix Layering"
Cohesion: 0.33
Nodes (6): Phase 2 — Fix Layering, Task 2.1: Move `_list_assets_from_disk` into storage, Task 2.2: Move the overlay render trigger into kernel, Task 2.3: Move `_apply_free_form_code` out of `ir/apply.py`, Task 2.4: Repair `kernel/__init__.py` exports, Task 2.5: Add the layering guard test

### Community 210 - "Phase 7 — Wire Orphaned Features + Final Polish"
Cohesion: 0.33
Nodes (6): Phase 7 — Wire Orphaned Features + Final Polish, Task 7.1: Wire the QC gate into the server render path, Task 7.2: Wire `silence_compress` into the silence-cuts flow, Task 7.3: Rename `kernel/render_service.py` → `kernel/render_jobs.py`, Task 7.4: Sync skills with code (harness_skills + qc-standards + remotion_motion), Task 7.5: Final verification pass

### Community 211 - "Open Edit Blueprint (fixed)"
Cohesion: 0.17
Nodes (11): Debugging each subsystem, Editing session (web UI), Hard rules (`tests/test_layering.py`), Layered architecture (corrected), MCP session (IDE), Mental model (one sentence), Open Edit Blueprint (fixed), Package map (not “exactly 4 layers”) (+3 more)

### Community 212 - "BRIEFING — 2026-07-23T13:32:22+03:00"
Cohesion: 0.17
Nodes (11): Active Timers, Artifact Index, BRIEFING — 2026-07-23T13:32:22+03:00, Current Parent, 🔒 Key Constraints, Key Decisions Made, Mission, 🔒 My Identity (+3 more)

### Community 213 - "Remotion motion graphics in Open Edit"
Cohesion: 0.33
Nodes (6): Agent workflow, License, Props example, Remotion motion graphics in Open Edit, Security, When to use which backend

### Community 214 - "Phase 0 — Stop the Bleeding (P0 runtime bugs)"
Cohesion: 0.40
Nodes (5): Phase 0 — Stop the Bleeding (P0 runtime bugs), Task 0.1: Fix broken pi_bridge imports, Task 0.2: Fix broken edit_graph_service import in app.py, Task 0.3: Fix RenderSnapshots dead fallback in projects.py, Task 0.4: Baseline green test suite

### Community 215 - "Phase 3 — Single Dispatcher, Single Validators"
Cohesion: 0.40
Nodes (5): Phase 3 — Single Dispatcher, Single Validators, Task 3.1: pi_bridge delegates to kernel tool_executor, Task 3.2: Delete the dead Pydantic validator, Task 3.3: Move render-job tool schemas into the registry, Task 3.4: Consolidate reference validation into `ir/validate.py`

### Community 216 - "Open Edit"
Cohesion: 0.40
Nodes (5): Docs, Install, License / status, Open Edit, What this repo is

### Community 217 - "Open Edit harness skills"
Cohesion: 0.40
Nodes (5): How hosts should load them, Not agent skills, Open Edit harness skills, Planning & QC, Start here

### Community 218 - "Remotion Licensing for Open Edit"
Cohesion: 0.50
Nodes (4): Company / Automators license, Free license (no signup), Open Edit policy, Remotion Licensing for Open Edit

### Community 219 - "test_run_trigger_render_returns_render_failed_on_nonzero_exit"
Cohesion: 0.33
Nodes (4): Subprocess returns exit 1 → ``error: render_failed: ...``., P10: the mode passed to ``_build_render_spec`` must be one of     'proxy', 'fina, test_run_trigger_render_returns_render_failed_on_nonzero_exit(), test_run_trigger_render_validates_mode_in_render_spec()

### Community 220 - "_looks_like_bwrap_unavailable"
Cohesion: 0.67
Nodes (3): _looks_like_bwrap_unavailable(), CompletedProcess, Return True if the process output indicates bwrap could not create     the names

### Community 225 - "1. Observation"
Cohesion: 0.17
Nodes (11): 1. Observation, 2. Logic Chain, 3. Caveats, 4. Conclusion, 5. Verification Method, Adversarial Edge Case Verification Results, Code Files Inspected, Handoff Report: Reviewer 2 (Milestone 2 - R2: Token-Efficient Phrase-Packed Transcript Tool) (+3 more)

### Community 226 - "BRIEFING — 2026-07-23T13:36:25Z"
Cohesion: 0.17
Nodes (11): Artifact Index, BRIEFING — 2026-07-23T13:36:25Z, Change Tracker, Current Parent, 🔒 Key Constraints, Key Decisions Made, Loaded Skills, Mission (+3 more)

### Community 227 - "BRIEFING — 2026-07-23T13:44:00Z"
Cohesion: 0.17
Nodes (11): Artifact Index, BRIEFING — 2026-07-23T13:44:00Z, Change Tracker, Current Parent, 🔒 Key Constraints, Key Decisions Made, Loaded Skills, Mission (+3 more)

### Community 228 - "BRIEFING — 2026-07-23T13:39:00Z"
Cohesion: 0.17
Nodes (11): Artifact Index, BRIEFING — 2026-07-23T13:39:00Z, Change Tracker, Current Parent, 🔒 Key Constraints, Key Decisions Made, Loaded Skills, Mission (+3 more)

### Community 229 - "BRIEFING — 2026-07-23T13:41:00Z"
Cohesion: 0.17
Nodes (11): Artifact Index, BRIEFING — 2026-07-23T13:41:00Z, Change Tracker, Current Parent, 🔒 Key Constraints, Key Decisions Made, Loaded Skills, Mission (+3 more)

### Community 230 - "BRIEFING — 2026-07-23T13:49:00+03:00"
Cohesion: 0.17
Nodes (11): Artifact Index, BRIEFING — 2026-07-23T13:49:00+03:00, Change Tracker, Current Parent, 🔒 Key Constraints, Key Decisions Made, Loaded Skills, Mission (+3 more)

### Community 231 - "AddRemotionCompositionOp"
Cohesion: 0.30
Nodes (11): AddRemotionCompositionOp, Add a React Remotion composition that materializes to a CAS clip.      ``entry_p, project_with_remotion(), MonkeyPatch, Path, IR + materialize tests for Remotion compositions., test_append_rejects_path_escape(), test_apply_add_and_remove_remotion_composition() (+3 more)

### Community 232 - "OpenEdit_Repair_Plan.md"
Cohesion: 0.17
Nodes (11): 10. Final Report Required From the Agent, 1. Executive Diagnosis, 2. Severity Model, 4. Target Architecture, 6. Required Test Matrix, 8. Coding Rules, 9. Definition of Done, Golden end-to-end workflow (+3 more)

### Community 233 - "Forensic Audit Report — Milestone 4 (Forensic Audit Gate)"
Cohesion: 0.18
Nodes (10): 1. Observation, 2. Logic Chain, 3. Caveats, 4. Conclusion, 5. Verification Method, Forensic Audit Report — Milestone 4 (Forensic Audit Gate), Overall Repository Test Suite Run, R1: Automatic 30ms Audio Micro-Fades (+2 more)

### Community 234 - "BRIEFING — 2026-07-23T13:49:06Z"
Cohesion: 0.18
Nodes (10): Artifact Index, Attack Surface, BRIEFING — 2026-07-23T13:49:06Z, Current Parent, 🔒 Key Constraints, Key Decisions Made, Mission, 🔒 My Identity (+2 more)

### Community 235 - "BRIEFING — 2026-07-23T13:47:23Z"
Cohesion: 0.18
Nodes (10): Artifact Index, Attack Surface, BRIEFING — 2026-07-23T13:47:23Z, Current Parent, 🔒 Key Constraints, Key Decisions Made, Mission, 🔒 My Identity (+2 more)

### Community 236 - "Handoff Report: Milestone 1 (R1: 30ms Audio Micro-Fades in MLT Emitter)"
Cohesion: 0.18
Nodes (10): 1. Execute Unit Tests, 1. Observation, 2. File Inspection, 2. Logic Chain, 3. Caveats, 3. Invalidation Conditions, 4. Conclusion, 5. Verification Method (+2 more)

### Community 237 - "Handoff Report: 30ms Audio Micro-Fades in MLT Emitter (Milestone 1 / R1)"
Cohesion: 0.18
Nodes (10): 1. Code Inspection Verification, 1. Observation, 2. Logic Chain, 2. Pytest Execution, 3. Caveats, 3. Invalidation Conditions, 4. Conclusion, 5. Verification Method (+2 more)

### Community 238 - "BRIEFING — 2026-07-23T10:37:46Z"
Cohesion: 0.18
Nodes (10): Artifact Index, Attack Surface, BRIEFING — 2026-07-23T10:37:46Z, Current Parent, 🔒 Key Constraints, Key Decisions Made, Mission, 🔒 My Identity (+2 more)

### Community 239 - "BRIEFING — 2026-07-23T13:37:30Z"
Cohesion: 0.18
Nodes (10): Artifact Index, Attack Surface, BRIEFING — 2026-07-23T13:37:30Z, Current Parent, 🔒 Key Constraints, Key Decisions Made, Mission, 🔒 My Identity (+2 more)

### Community 240 - "BRIEFING — 2026-07-23T13:40:40+03:00"
Cohesion: 0.18
Nodes (10): Artifact Index, Attack Surface, BRIEFING — 2026-07-23T13:40:40+03:00, Current Parent, 🔒 Key Constraints, Key Decisions Made, Mission, 🔒 My Identity (+2 more)

### Community 241 - "BRIEFING — 2026-07-23T13:40:05Z"
Cohesion: 0.18
Nodes (10): Artifact Index, Attack Surface, BRIEFING — 2026-07-23T13:40:05Z, Current Parent, 🔒 Key Constraints, Key Decisions Made, Mission, 🔒 My Identity (+2 more)

### Community 242 - "BRIEFING — 2026-07-23T10:45:00Z"
Cohesion: 0.18
Nodes (10): Artifact Index, Attack Surface, BRIEFING — 2026-07-23T10:45:00Z, Current Parent, 🔒 Key Constraints, Key Decisions Made, Mission, 🔒 My Identity (+2 more)

### Community 243 - "renderTimeline"
Cohesion: 0.31
Nodes (11): bindTimelineScrubbing(), copyPlayheadTimecode(), fitTimelineToWindow(), formatTimecode(), opPositionSec(), renderRuler(), renderTimeline(), secToPx() (+3 more)

### Community 244 - "Render Pipeline Fix Implementation Plan"
Cohesion: 0.20
Nodes (9): Global Constraints, Locked Interfaces, Render Pipeline Fix Implementation Plan, Task 1 (Track Q): Quality core — tiers, overrides, profiles, Task 2 (Track P): Frame-server pipe, Task 3 (Track S): Surfaces — jobs params, CLI, REST, agent tool, Task 4 (Track H): hwaccel emitter + cache key helper, Task 5 (serial): Orchestrator integration + end-to-end test (+1 more)

### Community 245 - "BRIEFING — 2026-07-23T10:52:47Z"
Cohesion: 0.20
Nodes (9): Artifact Index, Audit Progress, Audit Scope, BRIEFING — 2026-07-23T10:52:47Z, Current Parent, 🔒 Key Constraints, Key Decisions Made, Mission (+1 more)

### Community 246 - "Original User Request"
Cohesion: 0.20
Nodes (9): 2026-07-23T13:32:22+03:00, 2026-07-23T13:45:41+03:00, Acceptance Criteria, Automated Tests & Quality, Original User Request, R1. Automatic 30ms Audio Micro-Fades in MLT Emitter, R2. Token-Efficient Phrase-Packed Transcript Tool (`get_transcript_packed`), R3. Waveform Cut Inspection Image Generation (+1 more)

### Community 247 - "Handoff Report — Milestone 4 (Full Test Suite Regression Verification)"
Cohesion: 0.20
Nodes (9): 1. Observation, 2. Logic Chain, 3. Caveats, 4. Conclusion, 5. Verification Method, Handoff Report — Milestone 4 (Full Test Suite Regression Verification), New Feature Unit Tests (Milestone 4 Targets), Test Execution Summary (+1 more)

### Community 248 - "Handoff Report: Milestone 2 (R2: Token-Efficient Phrase-Packed Transcript Tool)"
Cohesion: 0.20
Nodes (9): 1. Observation, 2. Logic Chain, 3. Caveats, 4. Conclusion, 5.1 Files to Inspect, 5.2 Verification Commands, 5.3 Invalidation Conditions, 5. Verification Method (+1 more)

### Community 249 - "BRIEFING — 2026-07-23T13:56:20Z"
Cohesion: 0.20
Nodes (9): Artifact Index, Audit Progress, Audit Scope, BRIEFING — 2026-07-23T13:56:20Z, Current Parent, 🔒 Key Constraints, Key Decisions Made, Mission (+1 more)

### Community 250 - "state.js"
Cohesion: 0.27
Nodes (9): maybeLoadSourcePreview(), refreshTimeline(), selectEdit(), normalizeAssets(), normalizeEdits(), normalizeNotes(), normalizeRenders(), normalizeTimeline() (+1 more)

### Community 251 - "pyagent_generate_remotion_composition.py"
Cohesion: 0.28
Nodes (7): generate_remotion_composition(), Any, Path, Agent tool: append AddRemotionCompositionOp (and optionally scaffold)., Path, Functional coverage for Remotion TOOL_TABLE wrappers., test_remotion_tools_scaffold_write_and_append_graph_op()

### Community 252 - "Original User Request"
Cohesion: 0.22
Nodes (8): 2026-07-23T10:32:04Z, Acceptance Criteria, Automated Tests & Quality, Original User Request, R1. Automatic 30ms Audio Micro-Fades in MLT Emitter, R2. Token-Efficient Phrase-Packed Transcript Tool (`get_transcript_packed`), R3. Waveform Cut Inspection Image Generation, Requirements

### Community 253 - "BRIEFING — 2026-07-23T13:32:15+03:00"
Cohesion: 0.22
Nodes (8): Artifact Index, BRIEFING — 2026-07-23T13:32:15+03:00, 🔒 Key Constraints, Mission, 🔒 My Identity, Project Status, User Context, Victory Audit Status

### Community 254 - "BRIEFING — 2026-07-23T10:34:25Z"
Cohesion: 0.22
Nodes (8): Artifact Index, BRIEFING — 2026-07-23T10:34:25Z, Current Parent, Investigation State, 🔒 Key Constraints, Key Decisions Made, Mission, 🔒 My Identity

### Community 255 - "BRIEFING — 2026-07-23T10:35:10Z"
Cohesion: 0.22
Nodes (8): Artifact Index, BRIEFING — 2026-07-23T10:35:10Z, Current Parent, Investigation State, 🔒 Key Constraints, Key Decisions Made, Mission, 🔒 My Identity

### Community 256 - "BRIEFING — 2026-07-23T10:32:44Z"
Cohesion: 0.22
Nodes (8): Artifact Index, BRIEFING — 2026-07-23T10:32:44Z, Current Parent, Investigation State, 🔒 Key Constraints, Key Decisions Made, Mission, 🔒 My Identity

### Community 257 - "BRIEFING — 2026-07-23T10:36:15Z"
Cohesion: 0.22
Nodes (8): Artifact Index, BRIEFING — 2026-07-23T10:36:15Z, Current Parent, Investigation State, 🔒 Key Constraints, Key Decisions Made, Mission, 🔒 My Identity

### Community 258 - "BRIEFING — 2026-07-23T10:37:00Z"
Cohesion: 0.22
Nodes (8): Artifact Index, BRIEFING — 2026-07-23T10:37:00Z, Current Parent, Investigation State, 🔒 Key Constraints, Key Decisions Made, Mission, 🔒 My Identity

### Community 259 - "BRIEFING — 2026-07-23T10:38:50Z"
Cohesion: 0.22
Nodes (8): Artifact Index, BRIEFING — 2026-07-23T10:38:50Z, Current Parent, Investigation State, 🔒 Key Constraints, Key Decisions Made, Mission, 🔒 My Identity

### Community 260 - "BRIEFING — 2026-07-23T10:37:40Z"
Cohesion: 0.22
Nodes (8): Artifact Index, BRIEFING — 2026-07-23T10:37:40Z, Current Parent, Investigation State, 🔒 Key Constraints, Key Decisions Made, Mission, 🔒 My Identity

### Community 261 - "Project: Open Edit Features Implementation"
Cohesion: 0.22
Nodes (8): Architecture, Code Layout, Emitter ↔ MLT Engine, Interface Contracts, Milestones, Project: Open Edit Features Implementation, Transcription ↔ Agent Tools, Visual Verify ↔ FFmpeg

### Community 262 - "sample_frames"
Cohesion: 0.22
Nodes (9): Return deduped, clamped frame timestamps for a video of length     ``duration_s`, sample_frames(), All 4 duration tiers + 1-frame short case., Three timestamps within 0.1s collapse to one (use override_count to     force th, No frame is closer than 0.05s to either edge of the video., test_dedupes_close_timestamps(), test_sample_frames_tiered_by_duration(), test_short_video_one_frame() (+1 more)

### Community 263 - "Milestones"
Cohesion: 0.25
Nodes (7): Execution Plan: Open Edit 3 Features Implementation, Milestone 1: R1. Automatic 30ms Audio Micro-Fades in MLT Emitter, Milestone 2: R2. Token-Efficient Phrase-Packed Transcript Tool (`get_transcript_packed`), Milestone 3: R3. Waveform Cut Inspection Image Generation, Milestone 4: Full Suite Regression Verification & Final Sign-off, Milestones, Overview

### Community 264 - "Milestone 2 (R2): Token-Efficient Phrase-Packed Transcript Tool Handoff Report"
Cohesion: 0.25
Nodes (7): 1. Observation, 2. Logic Chain, 3. Caveats, 4. Conclusion, 5. Verification Method, Implementation Checklist for Implementer:, Milestone 2 (R2): Token-Efficient Phrase-Packed Transcript Tool Handoff Report

### Community 265 - "Summary of Fixes — Worker 1 Fix Agent (Milestone 1)"
Cohesion: 0.25
Nodes (7): 1. Code Changes (`open_edit/render/emitter.py`), 2. Test Updates & Additions (`tests/test_render_emitter.py`), 3. Verification Test Run & Output, Command Run:, `_emit_audio_micro_fade` Keyframe Calculation & Deduplication Fix:, Result:, Summary of Fixes — Worker 1 Fix Agent (Milestone 1)

### Community 266 - ".open-edit-launcher.sh"
Cohesion: 0.46
Nodes (7): is_server_up(), log(), notify(), open_browser(), OPEN_EDIT_PROJECTS_ROOT, .open-edit-launcher.sh script, wait_for_server()

### Community 267 - "test_pillar_headers.py"
Cohesion: 0.25
Nodes (5): Tests for sandbox header auto-injection and run_script., Code with existing header should pass through unchanged., test_header_auto_inject_missing(), test_header_auto_inject_present(), test_run_python_importable()

### Community 268 - "Current System Architecture (2026-07-25)"
Cohesion: 0.29
Nodes (6): Current System Architecture (2026-07-25), Media Fixtures, Motion Graphics Backends, Product Path, Stabilization Status (summary), Supported Runtime Boundary

### Community 269 - "Soft Handoff Report — Project Orchestrator (Gen 1 -> Gen 2)"
Cohesion: 0.29
Nodes (6): Active Subagents, Key Artifacts, Milestone State, Observation & Summary of Work Completed So Far, Remaining Work for Successor (Gen 2), Soft Handoff Report — Project Orchestrator (Gen 1 -> Gen 2)

### Community 270 - "Milestone 4 Verification (Run 2) Handoff Report"
Cohesion: 0.29
Nodes (6): 1. Observation, 2. Logic Chain, 3. Caveats, 4. Conclusion, 5. Verification Method, Milestone 4 Verification (Run 2) Handoff Report

### Community 271 - "Handoff Report: Milestone 1 (Explorer 3 - Corner Cases & Test Implementation)"
Cohesion: 0.29
Nodes (6): 1. Observation, 2. Logic Chain, 3. Caveats, 4. Conclusion, 5. Verification Method, Handoff Report: Milestone 1 (Explorer 3 - Corner Cases & Test Implementation)

### Community 272 - "Handoff Report: Milestone 3 (R3: Waveform Cut Inspection Image Generation)"
Cohesion: 0.29
Nodes (6): 1. Observation, 2. Logic Chain, 3. Caveats, 4. Conclusion, 5. Verification Method, Handoff Report: Milestone 3 (R3: Waveform Cut Inspection Image Generation)

### Community 273 - "Handoff Report: Waveform Cut Inspection Edge Case Analysis & Unit Test Strategy (Milestone 3 / R3)"
Cohesion: 0.29
Nodes (6): 1. Observation, 2. Logic Chain, 3. Caveats, 4. Conclusion, 5. Verification Method, Handoff Report: Waveform Cut Inspection Edge Case Analysis & Unit Test Strategy (Milestone 3 / R3)

### Community 274 - "Handoff Report — Reviewer 2 (Milestone 1: 30ms Audio Micro-Fades in MLT Emitter)"
Cohesion: 0.29
Nodes (6): 1. Observation, 2. Logic Chain, 3. Caveats, 4. Conclusion, 5. Verification Method, Handoff Report — Reviewer 2 (Milestone 1: 30ms Audio Micro-Fades in MLT Emitter)

### Community 275 - "Handoff Report — Milestone 2 Review (Token-Efficient Phrase-Packed Transcript Tool)"
Cohesion: 0.29
Nodes (6): 1. Observation, 2. Logic Chain, 3. Caveats, 4. Conclusion, 5. Verification Method, Handoff Report — Milestone 2 Review (Token-Efficient Phrase-Packed Transcript Tool)

### Community 276 - "Summary of Changes"
Cohesion: 0.29
Nodes (6): 1. `open_edit/render/emitter.py`, 2. `tests/test_render_emitter.py`, 3. Verification Commands Run & Outputs, Command:, Output:, Summary of Changes

### Community 277 - "Handoff Report — Worker 1 Fix Agent (Milestone 1)"
Cohesion: 0.29
Nodes (6): 1. Observation, 2. Logic Chain, 3. Caveats, 4. Conclusion, 5. Verification Method, Handoff Report — Worker 1 Fix Agent (Milestone 1)

### Community 278 - "Handoff Report — Milestone 1 (R1: Automatic 30ms Audio Micro-Fades in MLT Emitter)"
Cohesion: 0.29
Nodes (6): 1. Observation, 2. Logic Chain, 3. Caveats, 4. Conclusion, 5. Verification Method, Handoff Report — Milestone 1 (R1: Automatic 30ms Audio Micro-Fades in MLT Emitter)

### Community 279 - "Handoff Report: Milestone 2 (R2: Token-Efficient Phrase-Packed Transcript Tool)"
Cohesion: 0.29
Nodes (6): 1. Observation, 2. Logic Chain, 3. Caveats, 4. Conclusion, 5. Verification Method, Handoff Report: Milestone 2 (R2: Token-Efficient Phrase-Packed Transcript Tool)

### Community 280 - "Handoff Report — Milestone 3 (R3: Waveform Cut Inspection Image Generation)"
Cohesion: 0.29
Nodes (6): 1. Observation, 2. Logic Chain, 3. Caveats, 4. Conclusion, 5. Verification Method, Handoff Report — Milestone 3 (R3: Waveform Cut Inspection Image Generation)

### Community 281 - "Handoff Report — Victory Auditor"
Cohesion: 0.29
Nodes (6): 1. Observation, 2. Logic Chain, 3. Caveats, 4. Conclusion, 5. Verification Method, Handoff Report — Victory Auditor

### Community 282 - "Handoff Report — worker_m4_fix"
Cohesion: 0.29
Nodes (6): 1. Observation, 2. Logic Chain, 3. Caveats, 4. Conclusion, 5. Verification Method, Handoff Report — worker_m4_fix

### Community 283 - "Style memory"
Cohesion: 0.29
Nodes (6): Capture confirmed hints, Do not, Read before planning, Reuse later, Style memory, When to load

### Community 284 - "Style memory"
Cohesion: 0.29
Nodes (6): Capture confirmed hints, Do not, Read before planning, Reuse later, Style memory, When to load

### Community 285 - "Delivery Loop — Grok Orchestrator"
Cohesion: 0.33
Nodes (5): Current known issues (seed list), Delivery checklist (all must pass), Delivery Loop — Grok Orchestrator, Scope (do NOT change UI style), Worker protocol

### Community 286 - "Progress Tracking — Open Edit Features"
Cohesion: 0.33
Nodes (5): Checklist, Current Status, Iteration Status, Notes & Findings, Progress Tracking — Open Edit Features

### Community 287 - "Changes Summary — Milestone 3 (R3: Waveform Cut Inspection Image Generation)"
Cohesion: 0.33
Nodes (5): 1. `open_edit/serve/visual_verify.py`, 2. `tests/test_visual_verify_waveform.py` (New File), Changes Summary — Milestone 3 (R3: Waveform Cut Inspection Image Generation), Files Modified / Created, Test Verification Output

### Community 288 - "test_free_form_e2e.py"
Cohesion: 0.33
Nodes (5): Phase 3 Task 10: end-to-end tests for the free-form Python sandbox.  All tests s, L2: free-form + full render produces a non-empty mlt xml string., Probe whether the Rust sandbox can actually execute a trivial run.      Returns, _sandbox_runnable(), test_free_form_then_render()

### Community 289 - "7. First Implementation Batch"
Cohesion: 0.40
Nodes (5): 7. First Implementation Batch, Batch A — Tests first, Batch B — Canonical provider registry, Batch C — Upload and project creation, Batch D — Agent truthfulness

### Community 290 - "Changes Summary - Milestone 2 (Token-Efficient Phrase-Packed Transcript Tool)"
Cohesion: 0.50
Nodes (3): Changes Summary - Milestone 2 (Token-Efficient Phrase-Packed Transcript Tool), Modified & Created Files, Test Output

### Community 291 - "Victory Auditor Progress"
Cohesion: 0.50
Nodes (3): Status, Step Log, Victory Auditor Progress

### Community 292 - "Phase 1 — Unify Providers, Models, Capabilities, and Keys"
Cohesion: 0.50
Nodes (4): API shape, Done when, Phase 1 — Unify Providers, Models, Capabilities, and Keys, Tasks

### Community 293 - "Phase 10 — CI, Release Gates, and Documentation"
Cohesion: 0.50
Nodes (4): CI jobs, Documentation to update, Phase 10 — CI, Release Gates, and Documentation, Release gates

### Community 294 - "Phase 0 — Freeze Scope and Build a Reproduction Baseline"
Cohesion: 0.50
Nodes (4): Done when, Phase 0 — Freeze Scope and Build a Reproduction Baseline, Required baseline commands, Tasks

### Community 295 - "Phase 2 — Repair the Agent and Tool Protocol"
Cohesion: 0.50
Nodes (4): Done when, Phase 2 — Repair the Agent and Tool Protocol, Tasks, Tool-loop invariants

### Community 296 - "test_render_composited_returns_final_path_on_success"
Cohesion: 0.33
Nodes (4): Test 18: template not found in either dir raises OverlayRenderError., Test 38: returns the composited MP4 path on success., test_render_composited_returns_final_path_on_success(), test_template_not_found_raises_overlay_render_error()

### Community 297 - "test_serve_send_reconnect.py"
Cohesion: 0.50
Nodes (3): Tests for the v1.4 P2 review fix to the Send click path.  The original report (", Regression: clicking Send while the WS is in CONNECTING state     must kick a ``, test_handle_send_kicks_reconnect_when_ws_is_connecting()

### Community 301 - "Phase 3 — Secure and Stabilize HTTP/WebSocket Boundaries"
Cohesion: 0.67
Nodes (3): Done when, Phase 3 — Secure and Stabilize HTTP/WebSocket Boundaries, Tasks

### Community 302 - "Phase 4 — Repair Project Creation and Media Ingestion"
Cohesion: 0.67
Nodes (3): Done when, Phase 4 — Repair Project Creation and Media Ingestion, Tasks

### Community 303 - "Phase 8 — Integrate the Go and Python Paths"
Cohesion: 0.67
Nodes (3): Done when, Phase 8 — Integrate the Go and Python Paths, Tasks

### Community 304 - "test_run_trigger_render_overlay_inside_running_loop"
Cohesion: 0.67
Nodes (3): asyncio, V1: ``run_trigger_render`` with mode='overlay' must not raise     ``RuntimeError, test_run_trigger_render_overlay_inside_running_loop()

## Knowledge Gaps
- **912 isolated node(s):** `OPEN_EDIT_PROJECTS_ROOT`, `.open-edit-stop.sh script`, `run_loop.sh script`, `projectRoot`, `compositionId` (+907 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **65 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `EditGraphStore` connect `EditGraphStore` to `types.py`, `routers/projects.py`, `Timeline`, `test_serve_projects.py`, `NotesStore`, `edit_graph.py`, `Project`, `tool_executor.py`, `test_orchestrator_fails_hard_on_remotion_error`, `test_agent_tool_table_coverage.py`, `test_tools.py`, `IR`, `test_serve_pi_bridge.py`, `RenderJobService`, `execute_tool`, `test_serve_agent_visual_verify.py`, `RenderSnapshotStore`, `import_asset`, `._conn`, `_contract.py`, `open_conn`, `pi_bridge.py`, `test_long_form_e2e.py`, `test_visual_verify.py`, `run_free_form`, `cli.py`, `build_prior_state`, `test_sandbox_backends.py`, `compute_edit_graph_hash`, `kernel/__init__.py`, `tool_result`, `test_mcp_server.py`, `bridge.py`, `ProjectPaths`, `ensure_schema`, `now_iso8601`, `orchestrator.py`, `AddRemotionCompositionOp`, `AddClipOp`, `AssetStore`, `test_phase567_edit_render.py`, `Asset`, `staging.py`, `ops.py`, `TestPhase1Integrity`, `pyagent_generate_remotion_composition.py`, `run_trigger_render`?**
  _High betweenness centrality (0.113) - this node is a cross-community bridge._
- **Why does `Project` connect `Project` to `types.py`, `Timeline`, `edit_graph.py`, `eval_scenarios.py`, `IR`, `RenderJobService`, `TestOperationTypes`, `_contract.py`, `NarrativeSegment`, `HtmlOverlay`, `test_long_form_e2e.py`, `cli.py`, `test_apply_free_form.py`, `compute_edit_graph_hash`, `tool_result`, `ProjectPaths`, `ensure_schema`, `orchestrator.py`, `AddRemotionCompositionOp`, `AddClipOp`, `test_phase567_edit_render.py`, `Asset`, `staging.py`, `run_trigger_render`?**
  _High betweenness centrality (0.029) - this node is a cross-community bridge._
- **Why does `Timeline` connect `Timeline` to `types.py`, `compute_edit_graph_hash`, `materialize.py`, `orchestrator.py`, `Project`, `AddRemotionCompositionOp`, `AddClipOp`, `_overlay`, `_SlowPopen`, `eval_scenarios.py`, `HtmlOverlay`, `tests/test_html_overlay.py`, `generate_composition_html`, `test_serve_pi_bridge.py`, `test_run_trigger_render_overlay_inside_running_loop`, `_FakePopen`, `ensure_schema`, `run_trigger_render`?**
  _High betweenness centrality (0.028) - this node is a cross-community bridge._
- **Are the 36 inferred relationships involving `EditGraphStore` (e.g. with `_FlushingBuffer` and `_StoreBuffer`) actually correct?**
  _`EditGraphStore` has 36 INFERRED edges - model-reasoned connections that need verification._
- **Are the 24 inferred relationships involving `AddClipOp` (e.g. with `MotionTemplateParams` and `IR`) actually correct?**
  _`AddClipOp` has 24 INFERRED edges - model-reasoned connections that need verification._
- **Are the 19 inferred relationships involving `Timeline` (e.g. with `ApplyError` and `EmitterConfig`) actually correct?**
  _`Timeline` has 19 INFERRED edges - model-reasoned connections that need verification._
- **Are the 31 inferred relationships involving `Project` (e.g. with `_FlushingBuffer` and `_StoreBuffer`) actually correct?**
  _`Project` has 31 INFERRED edges - model-reasoned connections that need verification._