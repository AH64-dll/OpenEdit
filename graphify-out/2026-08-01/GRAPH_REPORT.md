# Graph Report - mlt-pipeline  (2026-08-01)

## Corpus Check
- 358 files · ~209,791 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 4815 nodes · 11233 edges · 225 communities (212 shown, 13 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 715 edges (avg confidence: 0.54)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `917a6b84`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- types.py
- get_slice
- AddClipOp
- test_serve_projects.py
- NotesStore
- app.py
- Project
- emit_timeline
- silence.py
- search_assets
- _render_spec
- get_adapter
- eval_scenarios.py
- stream_chat
- EditGraphStore
- test_tools.py
- IR
- test_serve_pi_bridge.py
- test_remotion_renderer.py
- llm/__init__.py
- discover_runtimes
- logging_setup.py
- cli_adapter.py
- RenderJobService
- execute_tool
- compact_history
- timeline_plan.py
- test_serve_agent_visual_verify.py
- RenderSnapshotStore
- AssetStore
- FreeFormResult
- import_asset
- ._conn
- load_llm_config
- TestOperationTypes
- app.js
- test_serve_agent.py
- get_asset_store
- NarrativeSegment
- validate_or_error
- diagnostics.py
- test_stream_chat_opencode.py
- test_serve_env.py
- WordAlignment
- HtmlOverlay
- pi_bridge.py
- tests/test_html_overlay.py
- test_serve_llm_pi.py
- html_overlay.py
- test_serve_errors.py
- test_serve_asset_stream.py
- test_long_form_e2e.py
- render_overlay_layer
- test_visual_verify.py
- run_free_form
- cli.py
- test_e2e_render.py
- test_serve_agent_cost.py
- ensure_remotion_scaffold
- tool_registry.py
- test_providers.py
- test_apply_free_form.py
- test_sandbox_backends.py
- get_asset_or_error
- test_catalog.py
- compute_edit_graph_hash
- showToast
- test_serve_ws.py
- encoder.py
- motion_graphics/templates/__init__.py
- kernel/__init__.py
- Asset
- bindEvents
- _generate_waveform_inspection_image
- chat.js
- test_agent_loop_stability.py
- package.json
- tool_result
- test_mcp_server.py
- make_error
- storage/assets.py
- test_serve_cost_badge.py
- bridge.py
- test_windows_mcp.py
- list_assets
- ProjectPaths
- compress_silence
- ProjectState
- test_opencode_adapter.py
- ensure_schema
- test_transcription_pack.py
- remotion_bridge.mjs
- test_serve_render_jobs.py
- test_challenger_empirical.py
- test_visual_verify_prune.py
- test_ir_api.py
- test_serve_verify_chip.py
- generate_visual
- materialize.py
- skills.py
- _node_harness.py
- orchestrator.py
- server.py
- serve/cost.py
- test_review_ui.py
- TestEditGraphStore
- _parse_full_session
- _SlowPopen
- visual_verify.py
- serve/agent/__init__.py
- history_store.py
- cap_tool_result
- boot
- loadLLMConfig
- test_cli.py
- test_serve_llm_config_api.py
- serve/projects.py
- test_serve_chat_status.py
- test_serve_search_assets.py
- derive_timeline
- _require_project
- TokenAuthMiddleware
- TestPhase1Integrity
- test_frozen_frames.py
- run_trigger_render
- test_serve_cost.py
- _coerce_event
- extension.ts
- post_project_note
- resolve_project_path
- pi_extension/package.json
- routers/projects.py
- test_orchestrator_fails_hard_on_remotion_error
- routers/config.py
- save_stored_key
- tool_executor.py
- compute_anthropic_cost
- compute_openai_cost
- run_qc_gate
- test_serve_loading_state.py
- Open Edit as a local MCP server
- _maybe_verify_render
- TimelineSummary
- Install Open Edit
- test_sandbox_observations.py
- seeded_project
- test_stream_chat_pi_refactor.py
- _StoreBuffer
- load_pricing
- lookup_pricing
- _FakePopen
- test_serve_module_structure.py
- list_black_frames
- test_huge_line_stream_no_limit_overrun
- test_timeline_full.py
- get_profile_path
- Checks (and what to do about a failure)
- test_end_to_end_overlay_composite
- _allow_tmp_workdir
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
- style_inject.py
- test_layering.py
- _load_assets_via_store
- harness_skills/README.md
- build_tool_schemas
- Phase 5 — Split God Files
- Tool-surface reference — the 4-pillar tools
- loader.py
- TimelineSnapshotStore
- set_pinned
- Tool-surface reference — the 4-pillar tools
- Real-world failure modes (watch for these)
- Free-form ops & effect catalog — reference
- test_pyagent_run_python.py
- test_orchestrator_timeout.py
- Phase 4 (cont.) — Tool Contract
- Free-form ops & effect catalog — reference
- Open Edit MCP reference
- Checks (and what to do about a failure)
- Remotion motion graphics in Open Edit
- Open Edit MCP reference
- OpenEdit Code Restructure Implementation Plan
- Phase 2 — Fix Layering
- Phase 7 — Wire Orphaned Features + Final Polish
- RemotionMaterializeError
- get_asset_file
- Remotion motion graphics in Open Edit
- Phase 0 — Stop the Bleeding (P0 runtime bugs)
- Phase 3 — Single Dispatcher, Single Validators
- Open Edit
- Open Edit harness skills
- Remotion Licensing for Open Edit
- test_run_trigger_render_returns_no_video_stream
- _looks_like_bwrap_unavailable
- routers/__init__.py
- ws/__init__.py

## God Nodes (most connected - your core abstractions)
1. `EditGraphStore` - 211 edges
2. `AddClipOp` - 164 edges
3. `Timeline` - 158 edges
4. `Project` - 131 edges
5. `apply_operation()` - 93 edges
6. `AssetStore` - 79 edges
7. `Asset` - 76 edges
8. `IR` - 71 edges
9. `derive_timeline()` - 69 edges
10. `new_id()` - 66 edges

## Surprising Connections (you probably didn't know these)
- `test_run_python_importable()` --indirect_call--> `run_python()`  [INFERRED]
  tests/test_pillar_headers.py → open_edit/agent/tools/pyagent_run_python.py
- `test_run_python_importable()` --indirect_call--> `run_python()`  [INFERRED]
  tests/test_pillar_tools.py → open_edit/agent/tools/pyagent_run_python.py
- `test_sandbox_error_is_exception()` --calls--> `SandboxError`  [EXTRACTED]
  tests/test_free_form_exceptions.py → open_edit/agent/exceptions.py
- `test_windows_default_sandbox_backend_is_dev()` --calls--> `get_sandbox_backend()`  [EXTRACTED]
  tests/test_windows_mcp.py → open_edit/agent/sandbox/backends.py
- `test_windows_explicit_bwrap_raises()` --calls--> `get_sandbox_backend()`  [EXTRACTED]
  tests/test_windows_mcp.py → open_edit/agent/sandbox/backends.py

## Import Cycles
- 3-file cycle: `open_edit/serve/agent/__init__.py -> open_edit/serve/agent/cli_turn.py -> open_edit/serve/agent/loop.py -> open_edit/serve/agent/__init__.py`

## Communities (225 total, 13 thin omitted)

### Community 0 - "types.py"
Cohesion: 0.15
Nodes (67): Bootstrap codegen: render ``_bootstrap.py`` for in-sandbox execution.  C2 prefer, Protocol, In-process IR API for free-form Python code (sandbox side).  Phase 3 Task 4: rea, Anything with a single-arg `append` (list, _FlushingBuffer, ...)., SupportsAppend, AddRemotionCompositionOp, AddTransitionOp, ChangeClipSpeedOp (+59 more)

### Community 1 - "get_slice"
Cohesion: 0.17
Nodes (15): pyagent_get_style_profile: returns the tag-gated style profile slice.  Per phase, Phase 4 T2: Style Memory (aggregate, retrieve, style_inject)., get_slice(), Any, Tag-gated style profile retrieval for system prompt injection.  Per phase4-desig, _trim_to_token_cap(), Phase 4 Task 3: tag-gated style profile retrieval., Per spec section 8.8: below confidence 0.2, category is omitted. (+7 more)

### Community 2 - "AddClipOp"
Cohesion: 0.07
Nodes (47): apply_operation(), _apply_normalize_audio(), _apply_set_audio_gain(), Audio operations: gain and normalize. Pure functions., Add a 'volume' effect tagged with the target_dbfs to the target.      Without a, _apply_change_clip_speed(), _apply_replace_clip_source(), _apply_ripple_delete_clip() (+39 more)

### Community 3 - "test_serve_projects.py"
Cohesion: 0.08
Nodes (41): get_project_state(), Return the full state of a project (assets, ops, notes, summary)., test_project_state_includes_graph_revision(), _make_real_asset(), _make_real_op(), _make_real_project(), projects_root_tmp(), asyncio (+33 more)

### Community 4 - "NotesStore"
Cohesion: 0.12
Nodes (20): pyagent_add_marker: agent-initiated flag, writes to NotesStore with source=agent, NotesStore, Update mutable fields on a note.          Accepts only the Pydantic-validated se, ReviewNote, TimestampAnchor, CompletedProcess, Path, CLI tests for `open_edit notes` (Phase 4 T6, M1: add + dismiss actions). (+12 more)

### Community 5 - "app.py"
Cohesion: 0.08
Nodes (34): exception_handler, FastAPI, diagnostics(), get_health(), health(), _http_exception_handler(), _lifespan(), Any (+26 more)

### Community 6 - "Project"
Cohesion: 0.04
Nodes (88): EffectCatalog, In-memory registry of effect specs loaded from YAML., AddEffectOp, Project, _effects_for_clip(), _get_default_catalog(), _known_clip_ids(), _known_effect_ids() (+80 more)

### Community 7 - "emit_timeline"
Cohesion: 0.12
Nodes (39): _Element, Clip, Track, _emit_audio_micro_fade(), _emit_filter(), emit_timeline(), _emit_transition(), EmitterConfig (+31 more)

### Community 8 - "silence.py"
Cohesion: 0.10
Nodes (31): AudioLevels, _ffmpeg(), get_audio_levels(), _has_audio_stream(), _last_stderr_line(), list_silence(), _parse_db(), _parse_overall_db() (+23 more)

### Community 9 - "search_assets"
Cohesion: 0.06
Nodes (61): _cache_clear(), _cache_get(), _cache_key(), _cache_put(), _freesound_api_key(), _freesound_attribution_required(), _freesound_attribution_text(), _http_get_json() (+53 more)

### Community 10 - "_render_spec"
Cohesion: 0.07
Nodes (58): generate_composition_html(), Generate the HyperFrames composition HTML for a Timeline's overlays.      No sub, _overlay(), Sibling-task cancellation: when a non-OverlayRenderError exception is raised, Build a minimal HtmlOverlay-shaped object for the composition tests., Sibling-task cancellation: when comp_html_task raises unexpectedly, the     orch, Persistent tmpdir cleanup: on failure, partial final.mp4 is unlinked., Persistent tmpdir cleanup: on overlay/subprocess failure, bg.mp4 is preserved (+50 more)

### Community 11 - "get_adapter"
Cohesion: 0.10
Nodes (28): get_adapter(), list_adapters(), Look up an adapter by name. Raises ``KeyError`` on unknown., Return the names of all registered adapters (sorted)., _cli_stream_for(), get_provider_models(), Return the model list for a provider.      For CLI providers, this may shell out, Name-bound CLI stream: resolves its adapter from the registry.      ``stream_cha (+20 more)

### Community 12 - "eval_scenarios.py"
Cohesion: 0.07
Nodes (54): _clip(), _derive(), _project(), Scenario Evaluation Suite for Open Edit — Phase 7.  Tests the IR/apply layer aga, Add then remove a clip, assert track is empty., Add clip then move it to a new position, assert new position., Add clip then trim in/out points, assert new in/out., Add clip then slip it, assert result stays within original bounds. (+46 more)

### Community 13 - "stream_chat"
Cohesion: 0.05
Nodes (44): _pi_extension_path(), Default: <open_edit>/serve/pi_extension/extension.ts, Stream an LLM response as a sequence of :class:`StreamEvent`.      ``messages``, stream_chat(), stream_chat with the pi provider spawns fake-pi, parses its JSON, yields events., test_stream_chat_uses_fake_pi(), _collect(), fake_anthropic_sdk() (+36 more)

### Community 14 - "EditGraphStore"
Cohesion: 0.04
Nodes (46): is_verify_disabled(), Path, Per-project metadata accessors for the open_edit server.  v1.5 added the ``verif, Return True if the project's ``verify_disabled`` flag is set.      Reads from th, EditGraphStore, SQLite-backed edit graph store.  One .db file per project. WAL mode for concurre, Record a command for idempotency. No-op if command_id exists., Return True if a command with the given id has been recorded. (+38 more)

### Community 15 - "test_tools.py"
Cohesion: 0.06
Nodes (67): add_marker(), Append a ReviewNote with source=agent at the given timestamp., generate_visual_for_segment(), Return an AddClipOp for a templated motion graphic.      Args:         args: {, get_pending_notes(), List pending notes. Default: first 10 full + count of rest., get_style_profile(), Return the style profile slice for ``args['op_type']``.      Args:         args: (+59 more)

### Community 16 - "IR"
Cohesion: 0.10
Nodes (21): IR, Any, Free-form Python IR API. Each method appends one Pydantic op to the buffer., Append AddRemotionCompositionOp; return composition_uid., Append AddHtmlOverlayOp; return overlay_id., Caller-supplied value wins; else fall back to the IR-level value., Append AddClipOp; return generated clip_id., new_id() (+13 more)

### Community 17 - "test_serve_pi_bridge.py"
Cohesion: 0.06
Nodes (46): _bootstrap_project(), _bridge_env(), asyncio, Path, Tests for ``open_edit.serve.pi_bridge``.  The bridge is the Python CLI that the, Nonexistent project path → structured error., Full add_marker + get_pending_notes roundtrip on a real project., The bridge auto-injects project_id (from EditGraphStore) when     the caller did (+38 more)

### Community 18 - "test_remotion_renderer.py"
Cohesion: 0.29
Nodes (9): fixture, MonkeyPatch, Path, Tests for the Remotion renderer wrapper (fake CLI; no Chromium)., remotion_project(), test_cache_key_stable_for_same_inputs(), test_render_composition_writes_props_file_and_output(), test_validate_entry_point_ok() (+1 more)

### Community 19 - "llm/__init__.py"
Cohesion: 0.10
Nodes (35): open_edit.serve — FastAPI chat-driven backend for the Open Edit video editor.  T, Any, Generic subprocess driver for CLI providers (pi, opencode, antigravity, jcode) +, Generic subprocess driver for any CLIAdapter (pi, opencode, ...).      Builds th, Pi provider — delegates to _stream_cli with the PiAdapter.      After _stream_cl, _stream_cli(), _stream_pi(), CLI-provider streaming: generic driver + pi wrapper. (+27 more)

### Community 20 - "discover_runtimes"
Cohesion: 0.14
Nodes (20): candidate_dirs(), discover_runtimes(), find_binary_in_expanded_path(), get_expanded_path_env(), Any, Path, v1.8 — Runtime Registry & GUI PATH Expansion.  All provider metadata is defined, Specification and status of an LLM runtime.      Fields are derived from the can (+12 more)

### Community 21 - "logging_setup.py"
Cohesion: 0.06
Nodes (44): Logger, LogRecord, bind_context(), ContextFilter, CorrelationIdMiddleware, get_context(), get_conversation_id(), get_job_id() (+36 more)

### Community 22 - "cli_adapter.py"
Cohesion: 0.04
Nodes (26): _AnthropicAdapter, _AntigravityAdapter, _BaseCLIAdapter, CLIAdapter, _JCodeAdapter, _normalize_pi_object(), _OpenAIAdapter, _opencode_models_via_cli() (+18 more)

### Community 23 - "RenderJobService"
Cohesion: 0.11
Nodes (25): JobStatus, public_job(), Connection, Path, Row, ValueError, Durable render scheduling and subprocess lifecycle management.  The service is d, Mark jobs interrupted by a prior service process as orphaned. (+17 more)

### Community 24 - "execute_tool"
Cohesion: 0.10
Nodes (36): execute_tool(), Run a tool by name, dispatching through     ``open_edit.agent.tools.TOOL_TABLE``, project_path(), fixture, Path, Server-side tool-execution idempotency (Phase 1: data integrity).  A re-delivere, An MCP-parity ``{"ok": False, ...}`` failure must not be cached as     a ``done`, test_different_command_id_not_falsely_deduped() (+28 more)

### Community 25 - "compact_history"
Cohesion: 0.10
Nodes (31): compact_history(), ContextBudget, count_tokens(), count_tokens_history(), count_tokens_message(), _has_tool_result(), Any, Token counting and sliding-window history truncation for context budget manageme (+23 more)

### Community 26 - "timeline_plan.py"
Cohesion: 0.13
Nodes (24): burn_overlays(), GraphicsOverlayError, OverlayClip, Path, RuntimeError, Burn Remotion (or other) fullscreen graphics onto a base melt MP4 via ffmpeg.  M, Raised when ffmpeg cannot burn graphics onto the base render., Overlay timed fullscreen clips onto ``base_mp4``; write ``output_mp4``. (+16 more)

### Community 27 - "test_serve_agent_visual_verify.py"
Cohesion: 0.10
Nodes (40): _fake_mp4(), _make_fake_project_state(), _make_mock_stream(), _patched_agent_with_render(), Any, asyncio, Path, v1.5: visual verification loop in the agent.  These tests exercise the new verif (+32 more)

### Community 28 - "RenderSnapshotStore"
Cohesion: 0.09
Nodes (24): new_version_id(), Return a fresh render-version id (``v_<hex12>``)., Path, Render snapshot recording into the RenderSnapshotStore (Phase 4 T4)., Resolve the SQLite path for a project's render snapshots.      Mirrors the chat-, Append a snapshot to the RenderSnapshotStore.      ``success=True`` records a `r, record_snapshot(), _snapshots_path() (+16 more)

### Community 29 - "AssetStore"
Cohesion: 0.10
Nodes (13): AssetStore, _hash_file(), _probe_media(), Path, Content-addressed media asset store., Path to the metadata sidecar JSON next to the CAS file., Ingest one or more files. Returns one Asset per input path.          Bug B regre, Rewrite an asset's sidecar with new word-level ``alignment``.          Used by b (+5 more)

### Community 30 - "FreeFormResult"
Cohesion: 0.07
Nodes (33): FreeFormResult, Result of a free-form Python run. Always returned, never raised.      success=Tr, Path, Execute the run and return a FreeFormResult (may raise         SandboxUnavailabl, H5: resolve at call time, not at module import.      P8: resolve via an absolute, H5: resolve at call time, not at module import.      The allow-list is three fix, H5: resolve at call time, not at module import.      Order matches the install c, resolve_binary() (+25 more)

### Community 31 - "import_asset"
Cohesion: 0.09
Nodes (37): _http_download(), import_asset(), _lookup_result(), Any, Path, pyagent_import_asset: download + ingest a third-party media asset.  Two entry sh, Read a search result back from the cache by ``result_id``.      Returns ``None``, Persist a search result so ``import_asset`` can look it up later.      Called by (+29 more)

### Community 32 - "._conn"
Cohesion: 0.11
Nodes (12): Any, Connection, OperationUnion, Return the project_meta table as a dict. Empty if no rows.          JSON-encoded, Set a single project_meta field. Persists immediately.          Non-string value, Append an operation. Returns the assigned sequence_num.          Validates the o, Load all operations in sequence_num order.          Each op carries its ``sequen, Update an operation's status (e.g. for undo/revert or supersede). (+4 more)

### Community 33 - "load_llm_config"
Cohesion: 0.12
Nodes (34): field_validator, _atomic_write_text(), LLMConfig, LLMConfigError, load_llm_config(), Any, BaseModel, Exception (+26 more)

### Community 34 - "TestOperationTypes"
Cohesion: 0.06
Nodes (4): Bug A4: ``rate`` must be > 0 (a 0 or negative rate would crash at render)., Bug A4: ``target_dbfs`` must be in [-100, 0] dBFS., Test suite for Pydantic operation types and helpers., TestOperationTypes

### Community 35 - "app.js"
Cohesion: 0.11
Nodes (31): applyTheme(), bindTimelineScrubbing(), COMMANDS, copyPlayheadTimecode(), filteredCommands, fitTimelineToWindow(), formatTimecode(), initTheme() (+23 more)

### Community 36 - "test_serve_agent.py"
Cohesion: 0.08
Nodes (33): _mock_execute_tool(), _mock_stream_chat(), patched_agent(), Any, asyncio, fixture, Path, Tests for ``open_edit.serve.agent``.  Mocks the LLM (``stream_chat``) and the to (+25 more)

### Community 37 - "get_asset_store"
Cohesion: 0.14
Nodes (21): get_asset_store(), Return the AssetStore rooted at <project>/.open_edit/assets., _allowlist_roots(), ingest_local(), _path_allowed(), Any, Path, pyagent_ingest_local: ingest local media files into the project CAS.  Paths must (+13 more)

### Community 38 - "NarrativeSegment"
Cohesion: 0.11
Nodes (30): analyze(), _analyze_rule_based(), _analyze_with_llm(), NarrativeSegment, BaseModel, Narrative analyzer skill: classify transcript segments into beat types.  Per pha, Analyze the asset's transcript and return narrative segments.      With use_llm=, Simple rule-based fallback: segment by 5s windows, classify by position. (+22 more)

### Community 39 - "validate_or_error"
Cohesion: 0.08
Nodes (33): _check_type(), Any, ValueError, Hand-rolled schema validation for Open Edit tool arguments.  Validates tool argu, Raised when tool arguments don't match the schema., Check that ``value`` matches ``expected_type``.      ``number`` accepts both ``i, Validate ``args`` against the schema for ``name``.      Raises ``SchemaValidatio, Return an error dict if validation fails, or None if valid. (+25 more)

### Community 40 - "diagnostics.py"
Cohesion: 0.10
Nodes (30): _chromium_available(), collect_diagnostics(), _config_summary(), _disk_free_bytes(), get_health(), _mlt_available(), System health & diagnostics collection for the open_edit server.  Provides three, Return a redacted subset of server config. NEVER includes secrets. (+22 more)

### Community 41 - "test_stream_chat_opencode.py"
Cohesion: 0.23
Nodes (15): fake_opencode(), fake_opencode_hang(), asyncio, fixture, MonkeyPatch, Path, End-to-end tests for the v1.7 opencode provider (track C)., R4 fix: a hanging CLI is killed and yields an error event. (+7 more)

### Community 42 - "test_serve_env.py"
Cohesion: 0.11
Nodes (17): Tests for ``open_edit.serve.serve_env``.  The module exposes typed config dictio, When the env var is set, ``hyperframes_bin`` is the env value     (no fallback t, OPEN_EDIT_HYPERFRAMES_BIN unset → ``hyperframes_bin`` is ``None``.      Sentinel, OPEN_EDIT_HYPERFRAMES_BIN=/foo/bar → returned verbatim., OPEN_EDIT_OVERLAY_TMPDIR unset → ``overlay_tmpdir`` is ``None``., OPEN_EDIT_OVERLAY_TMPDIR=/tmp/x → Path('/tmp/x').resolve()., OPEN_EDIT_HYPERFRAMES_TIMEOUT_SECONDS defaults to 3600 (int)., OPEN_EDIT_HYPERFRAMES_TIMEOUT_SECONDS=300 → 300. (+9 more)

### Community 43 - "WordAlignment"
Cohesion: 0.11
Nodes (32): find_silence_gaps(), no_word_split_check(), propose_cuts(), Silence cutter skill: propose cuts at silence gaps.  Per phase4-design-revised.m, Check if a cut at [t_start, t_end] splits any word.      A cut splits a word if, Find silence intervals >= ``threshold_ms`` in source time.      Returns a list o, Return gap-based cut suggestions for `asset`.      Each suggestion is a dict::, WordAlignment (+24 more)

### Community 44 - "HtmlOverlay"
Cohesion: 0.11
Nodes (20): AddHtmlOverlayOp, HtmlOverlay, Add an HTML/CSS/JS overlay (e.g. lower-third, title card, caption) that     will, Remove a previously added HTML overlay by its overlay_id., A rendered HTML/CSS/JS overlay composited on top of the video track.      Produc, RemoveHtmlOverlayOp, _base_project(), _overlay_op() (+12 more)

### Community 45 - "pi_bridge.py"
Cohesion: 0.26
Nodes (12): _emit(), _emit_error(), main(), Any, Path, Python bridge between the pi extension and ``open_edit.agent.tools``.  The TypeS, Print a JSON object to stdout, flush, exit 0., Print a structured error to stdout, exit 0 (so the TS layer sees     the error i (+4 more)

### Community 46 - "tests/test_html_overlay.py"
Cohesion: 0.07
Nodes (29): Return the path to the hyperframes binary.      Order of resolution (spec §5):, _resolve_hyperframes_bin(), v1.6: tests for the HTML overlay compositing module.  The module is split into 4, V2: render_overlay_layer.should_cancel must be Callable[[], bool] | None., V2: composite_with_background.should_cancel must be Callable[[], bool] | None., V2: _run_subprocess_with_cancel.should_cancel must be Callable[[], bool] | None., Pinned `node_modules/.bin/hyperframes` exists → it's returned, no warning., No pinned binary → bare `npx hyperframes`, WARNING logged with the prescribed me (+21 more)

### Community 47 - "test_serve_llm_pi.py"
Cohesion: 0.10
Nodes (24): _pi_binary(), _pi_normalize_event(), Compat: normalize one parsed pi JSON object (dict → events).      Kept as a modu, _collect(), fake_pi(), fixture, Tests for the ``pi`` provider in ``open_edit.serve.llm``.  We don't actually spa, Drop a fake `pi` script in tmp_path and point OPEN_EDIT_PI_BINARY at it. (+16 more)

### Community 48 - "html_overlay.py"
Cohesion: 0.09
Nodes (27): _assign_tracks(), _clip_id(), _disk_footprint_check(), _estimate_overlay_size_mb(), _inline_variables(), OverlayRenderError, Any, Exception (+19 more)

### Community 49 - "test_serve_errors.py"
Cohesion: 0.06
Nodes (37): parametrize, SimpleNamespace, projects_root_tmp(), asyncio, fixture, Tests for the v1.4 fast-fail readable-error contract.  Background (P0-1 in v1.4, GET /api/projects/{id} for a freshly-initialised project returns     the empty s, Connecting a WS to an unknown project sends an error event whose     message inc (+29 more)

### Community 50 - "test_serve_asset_stream.py"
Cohesion: 0.08
Nodes (28): Path, Tests for asset streaming in the Open Edit server.  Pins down v1.4 P0-2: a fresh, ``GET /api/projects/{id}`` returns assets whose ``url`` field     points at the, A GET on the asset's ``url`` returns the file with the right     ``Content-Type`, An mp4 asset served via the streaming route has     ``Content-Type: video/mp4``, A Range request returns 206 Partial Content with the right     ``Content-Range``, An unknown asset hash returns 404, not 500 (no exception leak)., An unknown project id returns 404 (not 500). (+20 more)

### Community 51 - "test_long_form_e2e.py"
Cohesion: 0.16
Nodes (17): BaseException, MusicTrack, BaseModel, Music selector skill: pick mood-matched tracks for narrative segments.  Per phas, Pick a music track per segment based on beat mood., select(), _is_rate_limit_error(), _make_synthetic_5min_asset() (+9 more)

### Community 52 - "render_overlay_layer"
Cohesion: 0.10
Nodes (28): Run the hyperframes CLI to render `comp_html_path` to `output_path`.      Return, render_overlay_layer(), _argv_of(), _make_popen_mock(), Return the argv list from a mocked subprocess.Popen call., Build a fake Popen instance for the cancellation-aware wrappers., Test 19: subprocess.Popen is called with shell=False (explicit)., Test 20: argv contains '--format mov' (not '--format mp4' or '--transparent'). (+20 more)

### Community 53 - "test_visual_verify.py"
Cohesion: 0.06
Nodes (47): encode_jpeg(), model_capability(), parse_verdict(), Any, Path, Extract a single frame from ``input_path`` to ``output_path`` as JPEG,     downs, Return the multimodal / image capability of a model.      Never raises — unknown, Find the first ``VERIFICATION: <X>`` line in ``text`` (case-insensitive).      R (+39 more)

### Community 54 - "run_free_form"
Cohesion: 0.04
Nodes (51): Run free-form Python in the sandbox. NEVER raises (C7).      `originating_note_i, run_free_form(), skipif, L3: a free-form script that raises an exception does NOT corrupt the graph., L1: ro-bound source raises OSError(EROFS). The script catches the     error and, The design's "Done when" criterion: 50-line script -> 50 child ops., L4: covers C6 -- `ir.add_clip(...)` returns cid, `ir.trim_clip(cid, ...)` works., test_chained_ops_succeed() (+43 more)

### Community 55 - "cli.py"
Cohesion: 0.12
Nodes (32): cmd_free_form(), cmd_init(), cmd_list(), cmd_mcp(), cmd_notes(), cmd_notes_add(), cmd_notes_dismiss(), cmd_notes_list() (+24 more)

### Community 56 - "test_e2e_render.py"
Cohesion: 0.33
Nodes (4): Path, End-to-end render test: ingest -> ops -> melt -> QC -> cache.  Ingest 3 fixture, Ingest 3 clips, add a transition, render via melt, verify QC gate., test_e2e_render_three_clips_with_transition()

### Community 57 - "test_serve_agent_cost.py"
Cohesion: 0.07
Nodes (32): _mock_stream_chat_with_usage(), patched_agent_with_cost(), fixture, Tests for v1.4 P1-3 cost-update plumbing in ``open_edit.serve.agent``.  The agen, The sidecar lives at ``<project>/.open_edit/cost.json`` —     alongside the conv, Return a stream_chat mock that yields the given usage events     before yielding, Like ``patched_agent`` in test_serve_agent.py, but routes     ``stream_chat`` to, When the LLM yields a ``usage`` event, the agent loop must     emit a ``cost_upd (+24 more)

### Community 58 - "ensure_remotion_scaffold"
Cohesion: 0.23
Nodes (14): ensure_remotion_scaffold(), Path, Frozen Remotion starter copied into each project's `.open_edit/remotion/`., Create the Remotion starter under ``.open_edit/remotion`` if missing., Return validation errors for AI-written Remotion TSX/TS source., Write a composition file after path + source validation., validate_composition_source(), write_composition_file() (+6 more)

### Community 59 - "tool_registry.py"
Cohesion: 0.36
Nodes (8): CancelRenderJobArgs, EditProjectArgs, GetRenderJobArgs, BaseModel, QueryProjectArgs, Pydantic-backed registry of Open Edit tool argument schemas.  Single source of t, RunScriptArgs, TriggerRenderArgs

### Community 60 - "test_providers.py"
Cohesion: 0.08
Nodes (30): _anthropic_stream(), list_provider_ids(), list_provider_specs(), list_visible_providers(), _openai_stream(), _pi_stream(), provider_default_model(), LLM provider registry — single source of truth.  Centralises the provider name → (+22 more)

### Community 61 - "test_apply_free_form.py"
Cohesion: 0.19
Nodes (12): Free-form script execution entry point (agent layer).  Task 2.3: moved from `ope, Run a free-form Python script in the sandbox and append its child ops.      Each, run_free_form_code(), minimal_project(), fixture, Task 2.3: run_free_form_code integration in agent/free_form.py.  Moved from open, Mocked sandbox returns 3 child ops; they are appended to the project., Sandbox returns failure → ApplyError; edit_graph unchanged. (+4 more)

### Community 62 - "test_sandbox_backends.py"
Cohesion: 0.10
Nodes (33): BwrapBackend, DevSubprocessBackend, get_sandbox_backend(), Exception, Free-form sandbox execution backends.  ``get_sandbox_backend()`` selects the bac, 5b: make a string safe to surface in a result detail.      - Take only the first, Pluggable execution backend for a free-form Python run.      A backend receives, Default, secure backend: the Rust ``open-edit-sandbox`` binary     (bwrap + secc (+25 more)

### Community 63 - "get_asset_or_error"
Cohesion: 0.11
Nodes (26): get_asset_or_error(), Exception, Base class for tool-domain errors surfaced as ``{"status": "error"}``., Tool error that should be retried later (e.g. transcription pending).      Norma, Look up an asset in the project's CAS.      Returns ``(asset, None)`` on success, Check an asset has word-level alignment.      Returns ``None`` when ``asset.alig, require_alignment(), ToolError (+18 more)

### Community 64 - "test_catalog.py"
Cohesion: 0.26
Nodes (11): catalog_dir(), fixture, Path, Tests for the EffectCatalog (YAML registry + validation gate)., Bug-hunt finding: the bundled catalog must contain all 10     spec-required effe, test_bundled_catalog_has_all_spec_required_effects(), test_catalog_get_returns_spec(), test_catalog_handles_empty_directory() (+3 more)

### Community 65 - "compute_edit_graph_hash"
Cohesion: 0.06
Nodes (50): compute_edit_graph_hash(), Canonical hashing of an edit graph for timeline snapshot caching., Return a stable sha256 hex digest for a list of operations.      Accepts op obje, cache_ttl_sec(), canonical_json_hash(), Any, Path, Filesystem-backed render cache, keyed by the edit-graph hash.  Single hash autho (+42 more)

### Community 66 - "showToast"
Cohesion: 0.18
Nodes (25): addAssetToTimeline(), addNoteAtPlayhead(), clearAssetsList(), deleteEdit(), hideEditDetail(), _isPlayableRender(), isProxyStale(), loadProjectState() (+17 more)

### Community 67 - "test_serve_ws.py"
Cohesion: 0.09
Nodes (23): _mock_execute_tool(), _mock_stream_chat(), patched_ws(), Any, fixture, Tests for the WebSocket chat endpoint.  Uses FastAPI's ``TestClient.websocket_co, Server sends a `ready` event right after accepting the WS., A full agent turn streams text → tool_start → tool_result → text → done. (+15 more)

### Community 68 - "encoder.py"
Cohesion: 0.08
Nodes (38): EncoderBackend, apply_profile_vcodec(), detect_gpu_vcodec(), EncoderSpec, _ffmpeg(), ffmpeg_video_args(), _probe_encoder(), Video encoder backend selection: GPU (default) or CPU.  Resolves the best availa (+30 more)

### Community 69 - "motion_graphics/templates/__init__.py"
Cohesion: 0.11
Nodes (15): button_cta(), Button template: call-to-action text on a bright background, static., cost_warning(), Cost template: warning-style text on a dark background, mild pulse., hook_fade_text(), Hook template: fade-in text on a colored background.  The render sandbox (W2) ex, Motion graphics templates, one per narrative beat type., mechanism_diagram() (+7 more)

### Community 70 - "kernel/__init__.py"
Cohesion: 0.15
Nodes (17): Shared editing kernel — tool dispatch, render jobs, pillar schemas.  Used by the, _apply_generated_ops(), dispatch_edit(), dispatch_generate(), dispatch_query(), Any, Path, Dispatch functions for the 4 pillar tools.  These functions route through the si (+9 more)

### Community 71 - "Asset"
Cohesion: 0.08
Nodes (19): Asset, fixture, Pytest configuration for open_edit tests., An isolated notes database file under a fresh tmp dir., A project with one asset pre-ingested, suitable for free-form runs (L9).      Se, tmp_notes_db(), tmp_project_with_assets(), _asset() (+11 more)

### Community 72 - "bindEvents"
Cohesion: 0.16
Nodes (21): autoGrowInput(), bindEvents(), executeCmd(), filterCmdList(), handleCmdKeydown(), handleFiles(), handleSend(), openCmdPalette() (+13 more)

### Community 73 - "_generate_waveform_inspection_image"
Cohesion: 0.11
Nodes (25): _generate_waveform_inspection_image(), _probe_streams(), Path, skipif, Unit tests for waveform cut inspection image generation (visual_verify.py).  The, When shutil.which('ffmpeg') returns None, return error status dict., Verify vstack command building, timing calculation, and filter structure., Local copy of the deleted ``visual_verify._probe_streams``. (+17 more)

### Community 74 - "chat.js"
Cohesion: 0.25
Nodes (18): appendErrorMessage(), appendRenderEvent(), appendSearchResults(), appendTextDelta(), appendToolCard(), appendUserMessage(), clearChatLog(), completeToolCard() (+10 more)

### Community 75 - "test_agent_loop_stability.py"
Cohesion: 0.13
Nodes (22): _db_path(), Return the edit_graph.db path for the given project directory.      Delegates to, _FakeState, _patch_common(), asyncio, Regression tests for the v1.9 agent-loop stability fixes.  Covers the root cause, The loop must NOT re-call stream_chat after tools complete (the old     bug: sec, The LLM retries the same failing call with identical args; after 3     attempts (+14 more)

### Community 76 - "package.json"
Cohesion: 0.10
Nodes (20): hyperframes, dependencies, react, react-dom, remotion, @remotion/cli, @remotion/renderer, description (+12 more)

### Community 77 - "tool_result"
Cohesion: 0.07
Nodes (47): F, Canonical tool result contract.  Every agent tool wrapper returns one of three s, Decorator: catch exceptions and return the canonical error dict.      ``ToolRetr, tool_result(), load_project(), make_ir(), _notes_db_path(), _project_root() (+39 more)

### Community 78 - "test_mcp_server.py"
Cohesion: 0.21
Nodes (20): dispatch_mcp_tool(), Path, Execute one MCP tool against the pinned project.      Returns a JSON-serializabl, project(), asyncio, fixture, Path, Tests for the local Open Edit MCP adapters and project binding. (+12 more)

### Community 79 - "make_error"
Cohesion: 0.18
Nodes (14): ErrorCodes, make_error(), Any, Exception, Unified error envelope for the Open Edit server.  Provides a single, dependency-, String constants for the unified error ``code`` field., Return a unified error envelope dict., Build an error envelope from an exception, stringifying its message. (+6 more)

### Community 80 - "storage/assets.py"
Cohesion: 0.13
Nodes (13): Content-addressed asset store with ffprobe metadata.  Layout: <assets_dir>/<sha2, _has_whisper(), Path, faster-whisper integration for word-level alignment.  Per phase4-design-revised., Resolve Whisper model size from arg or ``OPEN_EDIT_WHISPER_MODEL``., Resolve language override from arg or ``OPEN_EDIT_WHISPER_LANGUAGE``.      Empty, Transcribe an audio/video file to word-level alignment.      ``model_size`` defa, transcribe() (+5 more)

### Community 81 - "test_serve_cost_badge.py"
Cohesion: 0.10
Nodes (19): Tests for the cost badge in the chat UI (v1.4 P1-3).  The cost badge sits next t, Source=pi: render the per-turn + session cost in dollars., Source=computed (anthropic/openai): same dollar-format label     as pi. The sour, Source=unavailable: show the honest "cost n/a" message     instead of a fake $0., The cost badge factory is intentionally focused: it only     reacts to ``cost_up, The chat log's ``handleWsEvent`` must route ``cost_update``     events to the co, When source=pi or source=computed, the badge text contains     a $ glyph. Pinned, Until the first ``cost_update`` event arrives, the badge     should be hidden. T (+11 more)

### Community 82 - "bridge.py"
Cohesion: 0.12
Nodes (25): Exception, Exception types and result types for the free-form Python sandbox., Result of a render-sandbox run (Phase 4.5 W2).      Distinct from open_edit.rend, Raised for unrecoverable preflight/setup errors. NOT for runtime failures     (t, Internal: a single op in ops.jsonl failed referential or schema validation., RenderResult, SandboxError, _ValidationError (+17 more)

### Community 83 - "test_windows_mcp.py"
Cohesion: 0.09
Nodes (22): Path, Run heavy-compute code in the render sandbox. Returns a RenderResult     (never, P9: resolve a caller-supplied workdir.      The AI may operate on any directory;, run_render(), _validate_workdir(), RenderResult, P9 (loosened): a workdir that is a real project (has edit_graph.db)     is accep, P9: run_render also validates workdir. A workdir outside the allowed     root re (+14 more)

### Community 84 - "list_assets"
Cohesion: 0.27
Nodes (10): _is_derivative(), list_assets(), Any, pyagent_list_assets: list all ingested assets in the project.  Exported as ``lis, Return ingested assets for the project.      By default **excludes** Remotion re, Tests for the list_assets tool (Wave 1.2)., test_list_assets_no_assets_dir_is_empty(), test_list_assets_returns_empty_for_empty_project() (+2 more)

### Community 85 - "ProjectPaths"
Cohesion: 0.08
Nodes (33): pyagent_generate_visual_for_segment: render a templated motion graphic.  Per pha, apply_command(), _build_op(), EditGraphCommandError, open_store(), Any, Path, ValueError (+25 more)

### Community 86 - "compress_silence"
Cohesion: 0.13
Nodes (25): probe_duration(), Path, Return the container duration of ``path`` in seconds., build_keep_ranges(), compress_silence(), compress_silence_audio(), _concat_ranges(), extract_audio() (+17 more)

### Community 87 - "ProjectState"
Cohesion: 0.20
Nodes (14): _build_state_summary(), _build_system_prompt(), System prompt construction (DETERMINISTIC — see hard requirement #5)., Return a brief summary of the project state (under 1KB)., Build the system prompt.      Deterministic: the same ``state`` always produces, ProjectState, Full snapshot of a project returned by GET /api/projects/{id}., FakeProjectState (+6 more)

### Community 88 - "test_opencode_adapter.py"
Cohesion: 0.18
Nodes (19): _map_stop_reason(), normalize_opencode_line(), parse_opencode_events(), Any, v1.7 — opencode CLI event normalizer.  Reads a sequence of bytes from an ``openc, Read raw stdout lines from ``opencode run --format json`` and yield     ``Stream, Map opencode's ``part.tokens`` + ``part.cost`` to our usage shape., Map one raw stdout line to 0..n ``StreamEvent``-shaped dicts.      Blank / non-J (+11 more)

### Community 89 - "ensure_schema"
Cohesion: 0.18
Nodes (18): current_version(), ensure_schema(), _migration_files(), Connection, Path, Lightweight, safe SQLite migration runner for the edit-graph store.  Schema evol, Return the schema version recorded in ``PRAGMA user_version``., Map migration id -> SQL file path, discovered from this directory. (+10 more)

### Community 90 - "test_transcription_pack.py"
Cohesion: 0.21
Nodes (13): format_timestamp(), pack_transcript(), Format word alignments into silence-aware, speaker-grouped Markdown string., Format seconds into timestamp string MM:SS.ms (or HH:MM:SS.ms if >= 1hr)., Path, Unit tests for phrase-packed transcription formatting, tool handler, and registr, test_format_timestamp(), test_get_transcript_packed_tool() (+5 more)

### Community 91 - "remotion_bridge.mjs"
Cohesion: 0.11
Nodes (15): absEntry, absOut, absRoot, compositionId, concurrency, extraArgs, imageFormat, output (+7 more)

### Community 92 - "test_serve_render_jobs.py"
Cohesion: 0.13
Nodes (19): projects_root_tmp(), asyncio, fixture, Tests for the durable render-job lifecycle (v1.7+).  Background: the legacy in-m, Non-``proxy|final|overlay`` modes are rejected with 400 before     anything is e, Every enqueued job carries a ``created_at`` timestamp (float)., A job transitions queued → running → succeeded and records the     render output, A failing render lands in a terminal ``failed`` state with the     error recorde (+11 more)

### Community 93 - "test_challenger_empirical.py"
Cohesion: 0.19
Nodes (17): ProviderSpec, One LLM backend.      All metadata the server, UI, and dispatcher need to work w, client_and_project(), asyncio, fixture, MonkeyPatch, Path, TestClient (+9 more)

### Community 94 - "test_visual_verify_prune.py"
Cohesion: 0.19
Nodes (18): prune_images(), Return a copy of ``result`` with ``verification.frames`` removed.      Frame dat, Return a new slim view of ``history`` with image blocks stripped and     verific, _strip_verification_frames(), _make_tool_result_message(), _make_verification_result(), Tests for prune_images and _build_tool_result_message base64 dedup., test_prune_images_no_frames_unchanged() (+10 more)

### Community 95 - "test_ir_api.py"
Cohesion: 0.09
Nodes (9): ir_instance(), fixture, Phase 3 Task 4: IR API real implementation (12 methods, parent_id stamped)., H10: the buffer is a SupportsAppend; works with any list-like., Schema errors fail at build time (Pydantic ValidationError)., IR.add_effect must return the op's effect_id, distinct from edit_id.      Regres, test_add_effect_returns_canonical_effect_id(), test_ir_works_with_list_subclass() (+1 more)

### Community 96 - "test_serve_verify_chip.py"
Cohesion: 0.16
Nodes (17): v1.5: tests for the verification chip in the chat UI.  A small chip near the cha, On a ``verification_started`` event the chip should drop the     ``hidden`` clas, ``outcome=pass`` is the happy path: chip transitions to     ``verified`` (green), ``outcome=uncertain`` and ``outcome=failed`` both mean the visual     check didn, ``outcome=skipped`` is the path where the server itself decided     not to run v, ``outcome=capped`` is the path where the per-turn render cap     was hit. The ch, After a turn finishes, the chip must reset to ``idle`` and     re-hide. Per the, Run ``script_body`` (JS) through the harness and return the     ``(returncode, s (+9 more)

### Community 97 - "generate_visual"
Cohesion: 0.17
Nodes (15): generate_visual(), MotionTemplateParams, BaseModel, Path, Motion graphics engine: runs templates to produce video assets.  Per phase4-desi, Parameters consumed by every motion-graphics template.      ``asset_references``, Run a motion-graphics template, ingest the output, emit AddClipOp.      Args:, Phase 4.5 W7: motion graphics templated skill. (+7 more)

### Community 98 - "materialize.py"
Cohesion: 0.11
Nodes (36): _inject_clip(), _materialize_key(), materialize_remotion_compositions(), Path, Materialize Remotion compositions into CAS clips before MLT emit.  Fails hard on, Render pending Remotion compositions and inject clips onto tracks.      Mutates, _render_cache(), Remotion composition renderer for Open Edit.  Materializes React Remotion compos (+28 more)

### Community 99 - "skills.py"
Cohesion: 0.17
Nodes (17): __getattr__(), Local stdio MCP server — Open Edit as an agent plugin.  Exposes the pillar tools, list_skill_stems(), load_skill(), mcp_instructions(), Path, Load harness-facing skill markdown for MCP and other agent hosts.  Canonical fil, Short instructions injected on MCP initialize for any harness. (+9 more)

### Community 100 - "_node_harness.py"
Cohesion: 0.14
Nodes (15): app_js_path(), harness(), Path, Shared harness for the v1.4 Node-sandbox frontend tests.  The frontend (``open_e, Build a Node script that loads app.js as an ES module into a     stubbed browser, Write ``script`` to a temp file and run it with Node. The script     receives th, Absolute path to the app entry-point ES module.      Flat layout: ``tests/`` sit, run_node_script() (+7 more)

### Community 101 - "orchestrator.py"
Cohesion: 0.08
Nodes (32): MeltRunner, MeltTimeoutError, CompletedProcess, Exception, Path, Melt subprocess execution: command building, timeout, and cache mediation., Raised when melt exceeds its wall-clock budget., Build and run melt commands, mediating the render cache.      Cache lookup happe (+24 more)

### Community 102 - "server.py"
Cohesion: 0.16
Nodes (18): mcp_tool_schemas(), Any, Map MCP tool calls onto Open Edit pillar dispatch.  ``project_path`` is injected, Anthropic-shaped schemas for pillars + render helpers., Serialize a tool result for MCP TextContent., result_to_json(), build_server(), main() (+10 more)

### Community 103 - "serve/cost.py"
Cohesion: 0.20
Nodes (14): _accumulate_session_usage(), default_pi_sessions_dir(), encoded_cwd_segment(), find_pi_session_file(), _iter_files(), parse_pi_session_usage_delta(), Path, Cost computation for the Open Edit server (v1.4 P1-3).  Three responsibilities: (+6 more)

### Community 104 - "test_review_ui.py"
Cohesion: 0.27
Nodes (11): auto_proxy_enabled(), When set, the review UI may enqueue a proxy render after graph changes., client(), fixture, MonkeyPatch, TestClient, Tests for review-only UI mode and UI config API., test_llm_config_blocked_in_review_mode() (+3 more)

### Community 105 - "TestEditGraphStore"
Cohesion: 0.10
Nodes (4): Unit tests for SQLite-backed EditGraphStore., An optimistic reorder cannot overwrite a newer graph state., test_reorder_rejects_stale_graph_revision(), TestEditGraphStore

### Community 106 - "_parse_full_session"
Cohesion: 0.16
Nodes (15): _parse_full_session(), Path, Write one JSON object per line to ``path`` (UTF-8, trailing newline)., Local stand-in for the deleted ``cost_mod.parse_pi_session_usage``.      Full-fi, A session with 2 assistant messages: the parser sums their     usage.cost.total, Only assistant messages have usage data; user/tool messages     must be skipped, The delta variant only reads content appended after the last     position. Usefu, If the file shrank (e.g. pi's session was wiped), the delta     parser must NOT (+7 more)

### Community 107 - "_SlowPopen"
Cohesion: 0.14
Nodes (10): composite_with_background(), Composite the overlay MOV over the bg MP4 via ffmpeg.      Verifies the ffmpeg f, Fake Popen that stays alive until kill() is called., Cancellation during the render calls kill() and raises OverlayRenderError., Cancellation during ffmpeg calls kill() and raises OverlayRenderError., Test 29: ffmpeg non-zero exit → OverlayRenderError., _SlowPopen, test_composite_with_background_cancellation_kills_subprocess() (+2 more)

### Community 108 - "visual_verify.py"
Cohesion: 0.13
Nodes (16): build_qc_evidence(), build_verification_tool_result(), _is_summary(), v1.5 visual verification module.  Pure (or near-pure) functions for the post-ren, Collapse a deterministic QC gate report into a compact evidence block.      Cons, Build the structured ``trigger_render`` tool result with verification block., _verification_prompt(), Frames go inside the verification block of the tool result, NOT     in a synthet (+8 more)

### Community 109 - "serve/agent/__init__.py"
Cohesion: 0.11
Nodes (37): Any, Path, CLI-owned turns (pi / opencode / antigravity / jcode).  CLI providers run a COMP, Run one turn against a provider that owns its agent loop., _run_cli_owned_turn(), accumulate_usage(), _cost_sidecar_path(), _create_bg_task() (+29 more)

### Community 110 - "history_store.py"
Cohesion: 0.15
Nodes (24): append_to_conversation(), _build_tool_result_message(), _compact_jsonl(), _conversations_dir(), load_conversation(), new_conversation_id(), Any, Path (+16 more)

### Community 111 - "cap_tool_result"
Cohesion: 0.20
Nodes (15): cap_tool_result(), Any, Cap oversized tool results before they enter conversation history.  Called from, Return a copy of ``result`` with oversized fields truncated.      * Truncates ``, Tests for the result_capper module., test_custom_max_chars_honored(), test_error_field_truncated(), test_field_under_custom_max_chars_untouched() (+7 more)

### Community 112 - "boot"
Cohesion: 0.23
Nodes (13): boot(), refreshProjects(), renderProjectSelect(), selectProject(), createChatStatus(), createCostBadge(), createVerifyChip(), connectWS() (+5 more)

### Community 113 - "loadLLMConfig"
Cohesion: 0.18
Nodes (13): cancelTurn(), fetchLLMConfig(), loadLLMConfig(), populateModelDropdown(), populateProviderDropdown(), putLLMConfigRequest(), refreshSendGate(), saveLLMConfig() (+5 more)

### Community 114 - "test_cli.py"
Cohesion: 0.21
Nodes (13): CompletedProcess, Path, End-to-end CLI tests for open_edit init/list/summary/undo., `open_edit render` runs without error on an empty project (early return)., `--version` reports the version from package metadata, not a     hard-coded stri, Regression: `open_edit notes` (no subcommand) used to crash with     NameError b, _run(), test_init_ingests_videos() (+5 more)

### Community 115 - "test_serve_llm_config_api.py"
Cohesion: 0.26
Nodes (12): client_and_project(), fixture, MonkeyPatch, Path, TestClient, Tests for the GET/PUT /api/projects/{id}/llm-config REST routes., Antigravity is a valid provider — the adapter is registered., test_get_llm_config_returns_current_config() (+4 more)

### Community 116 - "serve/projects.py"
Cohesion: 0.09
Nodes (36): create_project(), _initialise_project(), _is_complete_render_mp4(), _is_project_folder(), list_projects(), list_renders(), _project_id_from_path(), ProjectInfo (+28 more)

### Community 117 - "test_serve_chat_status.py"
Cohesion: 0.17
Nodes (11): Tests for the frontend chat-status indicator (v1.4 P1-2).  The chat-status indic, The user-visible label for ``tool_running`` must include the tool     name (e.g., Per the brief, the indicator "clears within one frame of ``DONE``     or ``error, A second ``send()`` while the indicator is still showing the     previous turn m, ``window.OpenEdit.__testHooks.createChatStatus`` must exist so     tests can dri, A complete turn walks the indicator through every state and ends     back at idl, test_chat_status_error_then_done_clears(), test_chat_status_full_turn_lifecycle() (+3 more)

### Community 118 - "test_serve_search_assets.py"
Cohesion: 0.17
Nodes (11): Frontend tests for the v1.4 P1-1 search-assets results panel.  When the assistan, ``window.OpenEdit.__testHooks.appendSearchResults`` must exist so     tests can, The panel must produce one card per result, with the license     badge and "Add, Each card must surface the license string verbatim so the user     knows the ter, When the tool returns ``{error: "..."}``, the panel must show     the error (not, Clicking the "Add to project" button must trigger an     ``import_asset`` chat m, test_append_search_results_add_button_fires_import(), test_append_search_results_is_exposed_on_test_hooks() (+3 more)

### Community 119 - "derive_timeline"
Cohesion: 0.05
Nodes (40): list, _FlushingBuffer, Shared staging / collect / cleanup for free-form sandbox runs.  Both backends st, C6: validate each op against a working-copy timeline, then apply.      Reference, A list that writes each appended op to disk before keeping it.      H10: write F, _validate_ops_incrementally(), derive_timeline(), Timeline derivation: replay the edit graph into a Timeline. Pure functions. (+32 more)

### Community 120 - "_require_project"
Cohesion: 0.11
Nodes (34): delete, HTTPException, delete_op(), post_timeline_command(), JSONResponse, patch, post, Apply a manual timeline command through the shared edit-graph service. (+26 more)

### Community 121 - "TokenAuthMiddleware"
Cohesion: 0.17
Nodes (15): _extract_token(), _is_localhost(), BaseHTTPMiddleware, Request, Response, Fail-safe bearer-token auth with a localhost bypass.      Auth is only enforced, TokenAuthMiddleware, _ok_call_next() (+7 more)

### Community 123 - "test_frozen_frames.py"
Cohesion: 0.11
Nodes (29): FrozenFramesResult, FrozenSpan, list_frozen_frames(), _parse_freezedetect(), BaseModel, Frozen-frame detection for QC.  Wraps ffmpeg's ``freezedetect`` filter. A segmen, Return frozen-frame spans for ``video_path`` (any span ≥ ``min_sec``)., Parse freezedetect lines from ffmpeg's stderr.      freezedetect emits a ``freez (+21 more)

### Community 124 - "run_trigger_render"
Cohesion: 0.13
Nodes (25): _build_render_spec(), _load_timeline(), make_should_cancel(), _probe_duration(), Any, Path, Kernel-side overlay render trigger.  This module hosts the ``trigger_render`` to, Load the Timeline from the project's edit graph; returns an empty     Timeline i (+17 more)

### Community 125 - "test_serve_cost.py"
Cohesion: 0.17
Nodes (11): Tests for ``open_edit.serve.cost``.  Pure-function tests for the cost-computatio, Missing session file: the parser returns zeros (caller decides     whether to su, Find the file that ends with the session id, even when there's     a timestamp p, The session file is one level deep under sessions_dir (inside     the encoded-CW, No matching file → None (caller maps to ``unavailable``)., Missing sessions directory → None., test_find_pi_session_file_missing_returns_none(), test_find_pi_session_file_no_directory_returns_none() (+3 more)

### Community 126 - "_coerce_event"
Cohesion: 0.25
Nodes (10): _coerce_event(), Any, Tests for the StreamEvent contract (Wave 3.3)., StreamEvent must be importable and annotated — not just a docstring., A provider emitting a new event type should not crash the agent loop., test_coerce_event_fills_missing_text_with_empty_string(), test_coerce_event_handles_unknown_type_gracefully(), test_coerce_event_passes_through_valid_text_delta() (+2 more)

### Community 127 - "extension.ts"
Cohesion: 0.20
Nodes (4): OPEN_EDIT_PKG, REAL_DIR, REAL_FILE, ToolDef

### Community 128 - "post_project_note"
Cohesion: 0.10
Nodes (25): BackgroundTasks, get_thumbnail(), post_create_project(), post_ingest(), post_project_note(), Any, JSONResponse, Path (+17 more)

### Community 129 - "resolve_project_path"
Cohesion: 0.25
Nodes (8): ProjectPathError, Path, ValueError, Project path resolution for the local MCP server., Resolve and validate the project directory for MCP tool dispatch.      Preferenc, Raised when the MCP server cannot bind to a valid Open Edit project., resolve_project_path(), test_resolve_project_path_missing()

### Community 130 - "pi_extension/package.json"
Cohesion: 0.22
Nodes (8): description, main, name, private, scripts, check, type, version

### Community 131 - "routers/projects.py"
Cohesion: 0.16
Nodes (19): new_note_id(), Shared id and timestamp generators.  Single source of truth for UUIDs and ISO-86, Return a fresh review-note id (``note_<hex12>``)., CreateNoteRequest, CreateProjectRequest, BaseModel, Project routes: CRUD, ingest, notes, thumbnails., NoteSource (+11 more)

### Community 132 - "test_orchestrator_fails_hard_on_remotion_error"
Cohesion: 0.25
Nodes (9): fixture, MonkeyPatch, Path, skipif, Full proxy path: Remotion materialize then melt., Materialize failure must fail the render (no silent omission)., remotion_project(), test_orchestrator_fails_hard_on_remotion_error() (+1 more)

### Community 133 - "routers/config.py"
Cohesion: 0.14
Nodes (24): get_llm_config(), get_provider_models(), get_settings_keys(), get_ui_config(), list_discovered_runtimes(), LLMConfigRequest, LLMConfigResponse, put_llm_config() (+16 more)

### Community 134 - "save_stored_key"
Cohesion: 0.16
Nodes (20): _ensure_keys_file_dir(), get_masked_keys_summary(), get_stored_key(), load_all_stored_keys(), mask_key(), Any, Path, v1.8 — Secure Non-Technical BYOK (Bring Your Own Key) Store.  Stores user-entere (+12 more)

### Community 135 - "tool_executor.py"
Cohesion: 0.19
Nodes (20): LookupError, _cached_done_result(), execute_trigger_render(), _is_error_result(), _payload_hash(), Any, Path, Shared tool execution (Wave 3.2).  The agent loop (``agent.py``) and the TS-exte (+12 more)

### Community 136 - "compute_anthropic_cost"
Cohesion: 0.25
Nodes (8): compute_anthropic_cost(), Compute (turn_tokens, turn_cost_usd) for one Anthropic call.      ``usage`` is t, Unknown model → None (caller maps to ``unavailable`` source)., 1000 input + 500 output tokens of claude-sonnet-4-5:     input  = 1000 * 3.00 /, Cache hits/creation get their own per-1m rates., test_compute_anthropic_cost_basic_input_output(), test_compute_anthropic_cost_unknown_model_returns_none(), test_compute_anthropic_cost_with_cache()

### Community 137 - "compute_openai_cost"
Cohesion: 0.25
Nodes (8): compute_openai_cost(), Compute (turn_tokens, turn_cost_usd) for one OpenAI call.      ``usage`` is the, OpenAI's usage is ``prompt_tokens`` / ``completion_tokens``., OpenAI exposes cached prompt tokens under     ``prompt_tokens_details.cached_tok, Unknown model → None., test_compute_openai_cost_basic(), test_compute_openai_cost_unknown_model_returns_none(), test_compute_openai_cost_with_cached_tokens()

### Community 138 - "run_qc_gate"
Cohesion: 0.16
Nodes (18): BaseModel, Path, QCCheck, QCReport, QC gate — runs all 10 checks and aggregates the results.  Implements the check s, Run all QC checks against a rendered video file.      Parameters     ----------, run_qc_gate(), Tests for the QC gate (documented 6 checks + pipeline diagnostics). (+10 more)

### Community 139 - "test_serve_loading_state.py"
Cohesion: 0.25
Nodes (7): Tests for the v1.4 P2 loading state on the asset list.  The brief: "Asset list a, While ``api.getProjectState`` is in flight, the assets list     must show a load, When ``getProjectState`` fails, the assets list should not be     stuck on a loa, When the user switches projects, the assets list must NOT     keep showing the o, test_load_project_state_clears_loading_marker_on_error(), test_load_project_state_shows_loading_marker_during_fetch(), test_project_switch_shows_loading_state_not_stale_data()

### Community 140 - "Open Edit as a local MCP server"
Cohesion: 0.11
Nodes (19): Agent skills (all harnesses), Arabic transcription, Cursor config, How hosts load them, Initialize a project, Install, License, Linux / macOS (+11 more)

### Community 141 - "_maybe_verify_render"
Cohesion: 0.12
Nodes (18): _build_verification_result(), _maybe_verify_render(), Any, Path, Visual verification helpers (v1.5)., Map a render error string to a ``verdict_source`` value., Build a single ``verification_result`` AgentEvent., Run the verification stage for one ``trigger_render`` result.      Returns ``(ev (+10 more)

### Community 142 - "TimelineSummary"
Cohesion: 0.11
Nodes (19): asset_stream_url(), _asset_to_info(), AssetInfo, EffectInfo, _note_to_info(), OpInfo, _ops_to_info(), BaseModel (+11 more)

### Community 143 - "Install Open Edit"
Cohesion: 0.11
Nodes (18): 1. Clone, 2. Install the Python package (MCP), 3. Create an edit project, 4. Configure Cursor MCP, 5. Optional: review UI, 6. Smoke check, Install Open Edit, Linux / macOS (+10 more)

### Community 144 - "test_sandbox_observations.py"
Cohesion: 0.29
Nodes (3): Verify the strace observation fixtures are present and parseable.  The strace fi, Each strace file should list at least 5 distinct syscalls., test_strace_files_contain_real_syscalls()

### Community 145 - "seeded_project"
Cohesion: 0.29
Nodes (7): ffprobe_available(), projects_root_tmp(), fixture, True iff ``ffprobe`` is on PATH. Mirrors the pattern in     ``test_cli.py`` / ``, Point ``OPEN_EDIT_PROJECTS_ROOT`` at a fresh empty dir., A real, fully-initialised project under ``projects_root_tmp``.      Runs ``open_, seeded_project()

### Community 146 - "test_stream_chat_pi_refactor.py"
Cohesion: 0.21
Nodes (16): fake_pi(), asyncio, fixture, MonkeyPatch, Path, Regression tests for the _stream_pi → _stream_cli refactor (Phase 1).  These tes, The pi adapter from cli_adapter.py has the same name + timeout., Per-project .open_edit/config.toml must override env vars. (+8 more)

### Community 147 - "_StoreBuffer"
Cohesion: 0.40
Nodes (3): Any, Adapts an EditGraphStore to the IR's SupportsAppend protocol.      EditGraphStor, _StoreBuffer

### Community 148 - "load_pricing"
Cohesion: 0.29
Nodes (7): load_pricing(), Any, Load the pricing config from ``PRICING_PATH``.      Returns a nested dict: ``{pr, The shipped pricing.json has anthropic + openai sections., If the file doesn't exist (operator misconfig), we raise loudly     rather than, test_load_pricing_missing_file_raises(), test_load_pricing_returns_anthropic_and_openai_sections()

### Community 149 - "lookup_pricing"
Cohesion: 0.33
Nodes (6): lookup_pricing(), Look up the rate card for a provider/model.      Returns ``None`` if either the, Looking up a known model returns its entry., Unknown model returns None — caller maps to ``source: unavailable``., test_lookup_pricing_found(), test_lookup_pricing_unknown_model_returns_none()

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
Cohesion: 0.27
Nodes (13): _chmod(), _default_profile(), get_config_dir(), get_profile_path(), get_user_project_meta(), Path, Manages ~/.open-edit/ directory and config files., Return user-level (file-based) per-project metadata. Creates the file on first a (+5 more)

### Community 156 - "Checks (and what to do about a failure)"
Cohesion: 0.13
Nodes (14): Asset-reference failures at append, `audio_sync`, `black_frames`, Checks (and what to do about a failure), `duration`, `frozen_frames`, Over-aggressive cut density, `overlays_burned` (+6 more)

### Community 157 - "test_end_to_end_overlay_composite"
Cohesion: 0.67
Nodes (3): skipif, Test 41: actually run hyperframes + ffmpeg on a real project. Skipped     when h, test_end_to_end_overlay_composite()

### Community 158 - "_allow_tmp_workdir"
Cohesion: 0.67
Nodes (3): _allow_tmp_workdir(), fixture, P9: permit workdirs under the test's tmp_path by default.      Most tests use `t

### Community 163 - "Rules"
Cohesion: 0.14
Nodes (13): Color, audio, overlays — the free-form escape hatch, Cut dead air on sense boundaries, not raw gaps, Edit planning, Input, Match the target duration, Output, Pacing, Rules (+5 more)

### Community 166 - "Open Edit MCP — agent playbook"
Cohesion: 0.14
Nodes (14): Common recipes, Cut silence, `edit_project` generate (proposals — review then apply), `edit_project` operations (immediate), Hard rules (token savers), Ingest + put clips on timeline, Open Edit MCP — agent playbook, Priority order (+6 more)

### Community 168 - "open_conn"
Cohesion: 0.05
Nodes (35): now_iso8601(), Return the current UTC time as an ISO 8601 string., CommandStore, Path, SQLite-backed command idempotency store.  Tracks tool commands keyed by command_, SQLite store for command idempotency records., Record a command for idempotency. No-op if command_id exists., Return True if a command with the given id has been recorded. (+27 more)

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
Cohesion: 0.15
Nodes (13): Color, audio, overlays — the free-form escape hatch, Cut dead air on sense boundaries, not raw gaps, Edit planning, Input, Match the target duration, Output, Pacing, Rules (+5 more)

### Community 185 - "Phase 1 — Delete Dead Code"
Cohesion: 0.17
Nodes (12): Phase 1 — Delete Dead Code, Task 1.10: Delete `_ReadBackBuffer`, stale docstrings, orphaned skill, Task 1.11: Fix `cli.py` version string, Task 1.1: Delete `serve/_cli_patch.py`, Task 1.2: Delete the three serve shims, Task 1.3: Migrate pydantic_compat users and delete the shim, Task 1.4: Delete the legacy render-job registry in app.py, Task 1.5: Delete `ir/commutativity.py` (+4 more)

### Community 186 - "style_inject.py"
Cohesion: 0.26
Nodes (10): build_prior_state(), _format_slice(), _load_profile(), Builds the prior_state block for the system prompt.  Per phase4-design-revised.m, Phase 4 Task 3: prior_state block builder., Per audit M4: total <=600 tokens., Per spec section 8.7: pinned > profile_default > LLM_default., test_build_prior_state_format() (+2 more)

### Community 187 - "test_layering.py"
Cohesion: 0.29
Nodes (10): _imports_module(), _offenders(), _py_files(), Path, Layering guard tests.  Enforce the hard dependency rules: - kernel must never im, True if src contains an import statement for ``module`` (exact dotted-path compo, test_ir_never_imports_upper_layers(), test_kernel_never_imports_serve() (+2 more)

### Community 189 - "_load_assets_via_store"
Cohesion: 0.24
Nodes (9): _assets_dir_for_workdir(), _load_assets_via_store(), _load_project_for_validation(), Path, Build ``project.assets`` from every asset physically present in the     store's, Return the asset-store directory for a sandbox workdir.      The workdir is whic, Resolve from a sandbox workdir.          A workdir is the directory that directl, An asset present on disk (ingested, not yet used by any add_clip) must     still (+1 more)

### Community 190 - "harness_skills/README.md"
Cohesion: 0.22
Nodes (5): How hosts should load them, Not agent skills, Open Edit harness skills, Planning & QC, Start here

### Community 191 - "build_tool_schemas"
Cohesion: 0.24
Nodes (6): build_tool_schemas(), Return Anthropic-shaped tool schemas generated from the registry., Every TOOL_SCHEMAS name is a plain TOOL_TABLE entry or kernel-handled.      Kern, test_build_tool_schemas_names(), test_every_schema_tool_resolves_in_tool_table(), test_schema_additional_properties_and_required()

### Community 192 - "Phase 5 — Split God Files"
Cohesion: 0.22
Nodes (9): Phase 5 — Split God Files, Task 5.1: Split `serve/agent.py` into `serve/agent/` package, Task 5.2: Split `serve/app.py` into routers, Task 5.3: Split `serve/llm.py` into `serve/llm/` package, Task 5.4: Split `sandbox_bridge.py` into `agent/sandbox/`, Task 5.5: Split `ir/apply.py`, Task 5.6: Split `storage/edit_graph.py`, Task 5.7: Split `render/orchestrator.py` (+1 more)

### Community 193 - "Tool-surface reference — the 4-pillar tools"
Cohesion: 0.22
Nodes (9): 1. `query_project` (read-only), 2. `edit_project` (mutations + creative generation), 3. `run_script` (free-form Python), 4. `trigger_render`, Authoritative source, Common mistakes (do not repeat these), Priority order (always follow this), Relevant source (read these in the real codebase) (+1 more)

### Community 194 - "loader.py"
Cohesion: 0.25
Nodes (5): EffectSpec, ParamSpec, BaseModel, Path, Load the effect catalog from a directory of YAML files.

### Community 195 - "TimelineSnapshotStore"
Cohesion: 0.25
Nodes (4): Path, Path, SQLite store for derived timeline snapshots keyed by edit-graph hash., TimelineSnapshotStore

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

### Community 200 - "test_pyagent_run_python.py"
Cohesion: 0.25
Nodes (7): _captured_args(), Tests for the pyagent_run_python wrapper (agent/tools/).  The wrapper translates, Extract the kwargs that run_free_form was called with., I4: if the LLM forgets `parent_op_id`, the wrapper must supply a default     rat, I4 (sanity): when the LLM does supply parent_op_id, the wrapper     must not ove, test_run_python_explicit_parent_op_id_is_preserved(), test_run_python_missing_parent_op_id_gets_default()

### Community 201 - "test_orchestrator_timeout.py"
Cohesion: 0.32
Nodes (6): Path, Phase 4 T5 carry-over #2: render_project's TimeoutExpired branch must record a `, Set up `.open_edit/edit_graph.db` with one applied AddClipOp so     `render_proj, Per T5 carry-over #2: when melt times out, a `failed` snapshot is     appended t, _seed_project_with_one_op(), test_timeout_path_records_failed_snapshot()

### Community 202 - "Phase 4 (cont.) — Tool Contract"
Cohesion: 0.29
Nodes (7): Phase 4 (cont.) — Tool Contract, Task 4.1: Create the tool contract module, Task 4.2: Migrate the 12 simple tools to `@tool_result`, Task 4.3: Migrate asset-fetch boilerplate, Task 4.4: Migrate timeline_ops and remotion tools to canonical shapes, Task 4.5: Standardize parameter aliases, Task 4.6: Replace getattr dispatch with an explicit TOOL_TABLE

### Community 203 - "Free-form ops & effect catalog — reference"
Cohesion: 0.29
Nodes (7): Free-form ops & effect catalog — reference, Free-form ops (escape hatch), Relevant source (read these in the real codebase), Structured effect catalog, Validation gap — read this before using free-form, What you CANNOT do, When to escape to free-form

### Community 204 - "Open Edit MCP reference"
Cohesion: 0.29
Nodes (7): Authoritative code (debug Open Edit only), Dual process (MCP + review UI), Env knobs (config, not code), Example tool arguments, IR op kinds (high level), Open Edit MCP reference, When to use `run_script`

### Community 205 - "Checks (and what to do about a failure)"
Cohesion: 0.29
Nodes (7): `audio_sync`, `black_frames`, Checks (and what to do about a failure), `duration`, `frozen_frames`, `overlays_burned`, `streams`

### Community 206 - "Remotion motion graphics in Open Edit"
Cohesion: 0.29
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

### Community 211 - "RemotionMaterializeError"
Cohesion: 0.33
Nodes (5): A Remotion React composition pending materialization to a CAS clip.      Produce, RemotionComposition, RuntimeError, Raised when a Remotion composition cannot be materialized., RemotionMaterializeError

### Community 212 - "get_asset_file"
Cohesion: 0.33
Nodes (6): get_asset_file(), _guess_mime_type(), FileResponse, get, Stream an asset's bytes for the preview player.      v1.4 P0-2: without this rou, Best-effort mime type for a streamed asset.      Prefers the original filename's

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

### Community 219 - "test_run_trigger_render_returns_no_video_stream"
Cohesion: 0.33
Nodes (4): Subprocess returns exit 1 → ``error: render_failed: ...``., ffprobe finds no video stream → ``error: no_video_stream``., test_run_trigger_render_returns_no_video_stream(), test_run_trigger_render_returns_render_failed_on_nonzero_exit()

### Community 220 - "_looks_like_bwrap_unavailable"
Cohesion: 0.67
Nodes (3): _looks_like_bwrap_unavailable(), CompletedProcess, Return True if the process output indicates bwrap could not create     the names

## Knowledge Gaps
- **263 isolated node(s):** `projectRoot`, `compositionId`, `propsFile`, `output`, `pixelFormat` (+258 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **13 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `EditGraphStore` connect `EditGraphStore` to `post_project_note`, `types.py`, `test_serve_projects.py`, `routers/projects.py`, `test_orchestrator_fails_hard_on_remotion_error`, `Project`, `tool_executor.py`, `emit_timeline`, `NotesStore`, `TimelineSummary`, `test_tools.py`, `IR`, `test_serve_pi_bridge.py`, `_StoreBuffer`, `RenderJobService`, `execute_tool`, `test_serve_agent_visual_verify.py`, `FreeFormResult`, `import_asset`, `._conn`, `open_conn`, `pi_bridge.py`, `test_long_form_e2e.py`, `test_visual_verify.py`, `run_free_form`, `cli.py`, `test_e2e_render.py`, `style_inject.py`, `_load_assets_via_store`, `test_sandbox_backends.py`, `compute_edit_graph_hash`, `TimelineSnapshotStore`, `Asset`, `test_orchestrator_timeout.py`, `tool_result`, `test_mcp_server.py`, `bridge.py`, `ProjectPaths`, `ProjectState`, `orchestrator.py`, `TestEditGraphStore`, `serve/projects.py`, `derive_timeline`, `_require_project`, `TestPhase1Integrity`, `run_trigger_render`?**
  _High betweenness centrality (0.159) - this node is a cross-community bridge._
- **Why does `run_qc_gate()` connect `run_qc_gate` to `silence.py`, `get_thumbnail`, `probe_streams`, `cli.py`, `RenderJobService`, `list_black_frames`, `test_frozen_frames.py`?**
  _High betweenness centrality (0.064) - this node is a cross-community bridge._
- **Why does `StreamEvent` connect `llm/__init__.py` to `test_serve_ws.py`, `test_serve_agent.py`, `test_agent_loop_stability.py`, `stream_chat`, `test_serve_llm_pi.py`, `test_serve_errors.py`, `cli_adapter.py`, `test_serve_agent_cost.py`, `_coerce_event`?**
  _High betweenness centrality (0.046) - this node is a cross-community bridge._
- **Are the 36 inferred relationships involving `EditGraphStore` (e.g. with `_FlushingBuffer` and `_StoreBuffer`) actually correct?**
  _`EditGraphStore` has 36 INFERRED edges - model-reasoned connections that need verification._
- **Are the 24 inferred relationships involving `AddClipOp` (e.g. with `MotionTemplateParams` and `IR`) actually correct?**
  _`AddClipOp` has 24 INFERRED edges - model-reasoned connections that need verification._
- **Are the 19 inferred relationships involving `Timeline` (e.g. with `ApplyError` and `EmitterConfig`) actually correct?**
  _`Timeline` has 19 INFERRED edges - model-reasoned connections that need verification._
- **Are the 31 inferred relationships involving `Project` (e.g. with `_FlushingBuffer` and `_StoreBuffer`) actually correct?**
  _`Project` has 31 INFERRED edges - model-reasoned connections that need verification._