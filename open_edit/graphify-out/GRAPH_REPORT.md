# Graph Report - .  (2026-07-28)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 4199 nodes · 10398 edges · 202 communities (167 shown, 35 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 947 edges (avg confidence: 0.52)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `79f303eb`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Community 0
- Community 1
- Community 2
- Community 3
- Community 4
- Community 5
- Community 6
- Community 7
- Community 8
- Community 9
- Community 10
- Community 11
- Community 12
- Community 13
- Community 14
- Community 15
- Community 16
- Community 17
- Community 18
- Community 19
- Community 20
- Community 21
- Community 22
- Community 23
- Community 24
- Community 25
- Community 26
- Community 27
- Community 28
- Community 29
- Community 30
- Community 31
- Community 32
- Community 33
- Community 34
- Community 35
- Community 36
- Community 37
- Community 38
- Community 39
- Community 40
- Community 41
- Community 42
- Community 43
- Community 44
- Community 45
- Community 46
- Community 47
- Community 48
- Community 49
- Community 50
- Community 51
- Community 52
- Community 53
- Community 54
- Community 55
- Community 56
- Community 57
- Community 58
- Community 59
- Community 60
- Community 61
- Community 62
- Community 63
- Community 64
- Community 65
- Community 66
- Community 67
- Community 68
- Community 69
- Community 70
- Community 71
- Community 72
- Community 73
- Community 74
- Community 75
- Community 76
- Community 77
- Community 78
- Community 79
- Community 80
- Community 81
- Community 82
- Community 83
- Community 84
- Community 85
- Community 86
- Community 87
- Community 88
- Community 89
- Community 90
- Community 91
- Community 92
- Community 93
- Community 94
- Community 95
- Community 96
- Community 97
- Community 98
- Community 99
- Community 100
- Community 101
- Community 102
- Community 103
- Community 104
- Community 105
- Community 106
- Community 107
- Community 108
- Community 109
- Community 110
- Community 111
- Community 112
- Community 113
- Community 114
- Community 115
- Community 116
- Community 117
- Community 118
- Community 119
- Community 120
- Community 121
- Community 122
- Community 123
- Community 124
- Community 125
- Community 126
- Community 127
- Community 128
- Community 129
- Community 130
- Community 131
- Community 132
- Community 133
- Community 134
- Community 135
- Community 136
- Community 137
- Community 138
- Community 139
- Community 140
- Community 141
- Community 142
- Community 143
- Community 144
- Community 145
- Community 146
- Community 147
- Community 148
- Community 149
- Community 150
- Community 151
- Community 152
- Community 153
- Community 154
- Community 155
- Community 156
- Community 157
- Community 158
- Community 159
- Community 160
- Community 161
- Community 162
- Community 163
- Community 164
- Community 165
- Community 166
- Community 167
- Community 168
- Community 169
- Community 170
- Community 172
- Community 173
- Community 174
- Community 175
- Community 176
- Community 177
- Community 178
- Community 179
- Community 180
- Community 181
- Community 182
- Community 183
- Community 184
- Community 185
- Community 186
- Community 187
- Community 188
- Community 189
- Community 190
- Community 191
- Community 196

## God Nodes (most connected - your core abstractions)
1. `EditGraphStore` - 219 edges
2. `AddClipOp` - 173 edges
3. `Timeline` - 150 edges
4. `Project` - 142 edges
5. `AssetStore` - 96 edges
6. `apply_operation()` - 94 edges
7. `IR` - 77 edges
8. `Asset` - 73 edges
9. `AddEffectOp` - 73 edges
10. `NotesStore` - 73 edges

## Surprising Connections (you probably didn't know these)
- `test_header_auto_inject_missing()` --indirect_call--> `run_free_form()`  [INFERRED]
  tests/test_pillar_headers.py → open_edit/agent/sandbox_bridge.py
- `test_run_python_importable()` --indirect_call--> `run_python()`  [INFERRED]
  tests/test_pillar_headers.py → open_edit/agent/tools/pyagent_run_python.py
- `test_dispatch_query_unknown()` --calls--> `dispatch_query()`  [INFERRED]
  tests/test_pillar_tools.py → open_edit/kernel/pillar_tools.py
- `test_dispatch_edit_unknown()` --calls--> `dispatch_edit()`  [INFERRED]
  tests/test_pillar_tools.py → open_edit/kernel/pillar_tools.py
- `test_dispatch_generate_unknown()` --calls--> `dispatch_generate()`  [INFERRED]
  tests/test_pillar_tools.py → open_edit/kernel/pillar_tools.py

## Import Cycles
- None detected.

## Communities (202 total, 35 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.04
Nodes (82): derive_or_load_timeline(), derive_timeline(), Replay all non-reverted, applied operations in sequence order.      When ``stric, Return the Timeline for ``project``, using a cached snapshot when the     edit g, compute_edit_graph_hash(), Return a stable sha256 hex digest for a list of operations.      The hash is ord, Project, _known_clip_ids() (+74 more)

### Community 1 - "Community 1"
Cohesion: 0.06
Nodes (48): _apply_add_effect(), _apply_add_transition(), _apply_change_clip_speed(), _apply_free_form_code(), _apply_normalize_audio(), apply_operation(), _apply_remove_effect(), _apply_remove_keyframe() (+40 more)

### Community 2 - "Community 2"
Cohesion: 0.05
Nodes (72): build_prior_state(), _format_slice(), _load_profile(), Builds the prior_state block for the system prompt.  Per phase4-design-revised.m, pyagent_get_style_profile: returns the tag-gated style profile slice.  Per phase, pyagent_set_pinned_value: writes a pinned value to the style profile.  Per phase, _default_profile(), get_config_dir() (+64 more)

### Community 3 - "Community 3"
Cohesion: 0.18
Nodes (71): Result of a render-sandbox run (Phase 4.5 W2).      Distinct from open_edit.rend, RenderResult, BwrapBackend, DevSubprocessBackend, _FlushingBuffer, Exception, list, Python wrapper for the open-edit-sandbox Rust binary.  Phase 3 Task 8: orchestra (+63 more)

### Community 4 - "Community 4"
Cohesion: 0.06
Nodes (78): BackgroundTasks, delete, exception_handler, FileResponse, get, HTTPException, JSONResponse, cancel_render_job() (+70 more)

### Community 5 - "Community 5"
Cohesion: 0.04
Nodes (71): _accumulate_session_usage(), compute_anthropic_cost(), compute_openai_cost(), default_pi_sessions_dir(), encoded_cwd_segment(), find_pi_session_file(), _iter_files(), load_pricing() (+63 more)

### Community 6 - "Community 6"
Cohesion: 0.08
Nodes (34): pyagent_add_marker: agent-initiated flag, writes to NotesStore with source=agent, cmd_notes_add(), `open_edit notes add` — append a note to a project (M1)., NotesStore, _NoteUpdate, OpAnchor, BaseModel, Path (+26 more)

### Community 7 - "Community 7"
Cohesion: 0.05
Nodes (58): BlackFramesResult, BlackSpan, list_black_frames(), _parse_blackdetect(), BaseModel, Black-frame detection for QC.  Wraps ffmpeg's blackdetect filter. A frame is "bl, Return black-frame spans for the [in_sec, out_sec] range., Parse blackdetect lines from ffmpeg's stderr. (+50 more)

### Community 8 - "Community 8"
Cohesion: 0.05
Nodes (44): _pi_extension_path(), TypedDict, Default: <open_edit>/serve/pi_extension/extension.ts, One event yielded by :func:`stream_chat`.      Variants (the ``type`` field disc, StreamEvent, _collect(), fake_anthropic_sdk(), fake_pi_with_usage() (+36 more)

### Community 9 - "Community 9"
Cohesion: 0.08
Nodes (35): _effects_for_clip(), OperationUnion, I2 (final-fixes): validate referential integrity for every op type.      Before, _validate_references(), IR, Any, Free-form Python IR API. Each method appends one Pydantic op to the buffer., Append AddRemotionCompositionOp; return composition_uid. (+27 more)

### Community 10 - "Community 10"
Cohesion: 0.06
Nodes (61): _cache_clear(), _cache_get(), _cache_key(), _cache_put(), _freesound_api_key(), _freesound_attribution_required(), _freesound_attribution_text(), _http_get_json() (+53 more)

### Community 11 - "Community 11"
Cohesion: 0.06
Nodes (33): EditGraphStore, Any, Connection, OperationUnion, Path, Return the project_meta table as a dict. Empty if no rows.          JSON-encoded, Set a single project_meta field. Persists immediately.          Non-string value, Append an operation. Returns the assigned sequence_num.          Validates the o (+25 more)

### Community 12 - "Community 12"
Cohesion: 0.05
Nodes (50): FreeFormResult, Exception, Exception types and result types for the free-form Python sandbox., Result of a free-form Python run. Always returned, never raised.      success=Tr, Raised for unrecoverable preflight/setup errors. NOT for runtime failures     (t, Internal: a single op in ops.jsonl failed referential or schema validation., SandboxError, _ValidationError (+42 more)

### Community 13 - "Community 13"
Cohesion: 0.08
Nodes (33): ExitCode, JobStatus, LookupError, public_job(), Connection, Path, Row, ValueError (+25 more)

### Community 14 - "Community 14"
Cohesion: 0.07
Nodes (51): FastAPI, get_projects(), _lifespan(), asset_stream_url(), _asset_to_info(), AssetInfo, create_project(), EffectInfo (+43 more)

### Community 15 - "Community 15"
Cohesion: 0.10
Nodes (45): _Element, Clip, BaseModel, Track, _emit_audio_micro_fade(), _emit_filter(), emit_timeline(), _emit_transition() (+37 more)

### Community 16 - "Community 16"
Cohesion: 0.08
Nodes (42): BaseException, MusicTrack, BaseModel, Music selector skill: pick mood-matched tracks for narrative segments.  Per phas, Pick a music track per segment based on beat mood., select(), analyze(), _analyze_rule_based() (+34 more)

### Community 17 - "Community 17"
Cohesion: 0.08
Nodes (47): get_pending_notes(), List pending notes. Default: first 10 full + count of rest., get_style_profile(), Return the style profile slice for ``args['op_type']``.      Args:         args:, Return music-bed AddEffectOps for `args['asset_hash']`.      Args:         args:, select_music(), Set pinned key=value in the global style profile., set_pinned_value() (+39 more)

### Community 18 - "Community 18"
Cohesion: 0.06
Nodes (47): _bootstrap_project(), _bridge_env(), Path, Tests for ``open_edit.serve.pi_bridge``.  The bridge is the Python CLI that the, Nonexistent project path → structured error., Full add_marker + get_pending_notes roundtrip on a real project., The bridge auto-injects project_id (from EditGraphStore) when     the caller did, ``--list-tools`` returns the 4 pillar tool names. (+39 more)

### Community 19 - "Community 19"
Cohesion: 0.07
Nodes (39): New agent tools for Phase 4 Task 7.  This package is the home for the 5 new tool, add_marker(), Append a ReviewNote with source=agent at the given timestamp., analyze_narrative(), pyagent_analyze_narrative: returns narrative segments for the asset.  Per phase4, Return narrative segments for `args['asset_hash']`.      Args:         args: {"a, generate_remotion_composition(), Any (+31 more)

### Community 20 - "Community 20"
Cohesion: 0.10
Nodes (42): _cache_path(), _inject_clip(), _load_cache(), materialize_remotion_compositions(), Path, RuntimeError, Materialize Remotion compositions into CAS clips before MLT emit.  Fails hard on, Raised when a Remotion composition cannot be materialized. (+34 more)

### Community 21 - "Community 21"
Cohesion: 0.08
Nodes (45): AgentEvent, append_to_conversation(), _build_tool_result_message(), _build_verification_result(), _compact_jsonl(), _conversations_dir(), _cost_sidecar_path(), _create_bg_task() (+37 more)

### Community 22 - "Community 22"
Cohesion: 0.08
Nodes (44): get_project_state(), Return the full state of a project (assets, ops, notes, summary)., _make_real_asset(), _make_real_op(), _make_real_project(), projects_root_tmp(), asyncio, fixture (+36 more)

### Community 23 - "Community 23"
Cohesion: 0.06
Nodes (45): _overlay(), skipif, Sibling-task cancellation: when a non-OverlayRenderError exception is raised, Build a minimal HtmlOverlay-shaped object for the composition tests., Sibling-task cancellation: when comp_html_task raises unexpectedly, the     orch, Persistent tmpdir cleanup: on overlay/subprocess failure, bg.mp4 is preserved, Test 1: root has data-composition-id, data-start=0, data-duration=<bg_total>,, Test 5: clip div's data-start/data-duration/data-track-index     match the HtmlO (+37 more)

### Community 24 - "Community 24"
Cohesion: 0.08
Nodes (38): Logger, LogRecord, bind_context(), ContextFilter, get_context(), get_conversation_id(), get_job_id(), get_logger() (+30 more)

### Community 25 - "Community 25"
Cohesion: 0.08
Nodes (39): HtmlOverlay, A rendered HTML/CSS/JS overlay composited on top of the video track.      Produc, _assign_tracks(), _clip_id(), composite_with_background(), _disk_footprint_check(), _estimate_overlay_size_mb(), generate_composition_html() (+31 more)

### Community 26 - "Community 26"
Cohesion: 0.09
Nodes (36): compact_history(), ContextBudget, count_tokens(), count_tokens_history(), count_tokens_message(), _has_tool_result(), Any, Token counting and sliding-window history truncation for context budget manageme (+28 more)

### Community 27 - "Community 27"
Cohesion: 0.09
Nodes (36): burn_overlays(), GraphicsOverlayError, OverlayClip, Path, RuntimeError, Burn Remotion (or other) fullscreen graphics onto a base melt MP4 via ffmpeg.  M, Raised when ffmpeg cannot burn graphics onto the base render., Overlay timed fullscreen clips onto ``base_mp4``; write ``output_mp4``. (+28 more)

### Community 28 - "Community 28"
Cohesion: 0.11
Nodes (40): Run one full agent turn (user message -> final assistant text).      Yields :cla, run_agent_turn(), _fake_mp4(), _make_fake_project_state(), _make_mock_stream(), _patched_agent_with_render(), Any, asyncio (+32 more)

### Community 29 - "Community 29"
Cohesion: 0.09
Nodes (20): BaseModel, Enum, Path, str, RenderSnapshotStore for version-switchable render history.  Per phase4-design-re, Per audit M1: evict oldest status=ready; never evict rendering/failed., Return the most recent snapshot for the project, regardless of status., RenderSnapshot (+12 more)

### Community 30 - "Community 30"
Cohesion: 0.09
Nodes (16): AssetStore, _hash_file(), _probe_media(), Path, Ingest one or more files. Returns one Asset per input path.          Bug B regre, Rewrite an asset's sidecar with new word-level ``alignment``.          Used by b, Compute SHA-256 of a file as a hex string., Run ffprobe on a media file and return parsed metadata. (+8 more)

### Community 31 - "Community 31"
Cohesion: 0.09
Nodes (37): _http_download(), import_asset(), _lookup_result(), Any, Path, pyagent_import_asset: download + ingest a third-party media asset.  Two entry sh, Read a search result back from the cache by ``result_id``.      Returns ``None``, Persist a search result so ``import_asset`` can look it up later.      Called by (+29 more)

### Community 32 - "Community 32"
Cohesion: 0.12
Nodes (34): field_validator, _atomic_write_text(), LLMConfig, LLMConfigError, load_llm_config(), Any, BaseModel, Exception (+26 more)

### Community 33 - "Community 33"
Cohesion: 0.07
Nodes (37): Run free-form Python in the sandbox. NEVER raises (C7).      `originating_note_i, run_free_form(), L3: a free-form script that raises an exception does NOT corrupt the graph., L1: ro-bound source raises OSError(EROFS). The script catches the     error and, The design's "Done when" criterion: 50-line script -> 50 child ops., L4: covers C6 -- `ir.add_clip(...)` returns cid, `ir.trim_clip(cid, ...)` works., test_chained_ops_succeed(), test_free_form_failure_does_not_corrupt_graph() (+29 more)

### Community 34 - "Community 34"
Cohesion: 0.08
Nodes (26): CLIAdapter, Protocol, One CLI backend. Stateless; methods only., open_edit.serve — FastAPI chat-driven backend for the Open Edit video editor.  T, _api_key(), effective_provider(), _max_tokens(), _message_plain_text() (+18 more)

### Community 35 - "Community 35"
Cohesion: 0.06
Nodes (6): now_iso8601(), Return the current UTC time as an ISO 8601 string., Bug A4: ``rate`` must be > 0 (a 0 or negative rate would crash at render)., Bug A4: ``target_dbfs`` must be in [-100, 0] dBFS., Test suite for Pydantic operation types and helpers., TestOperationTypes

### Community 36 - "Community 36"
Cohesion: 0.08
Nodes (34): _mock_execute_tool(), _mock_stream_chat(), patched_agent(), Any, asyncio, fixture, Path, StreamEvent (+26 more)

### Community 37 - "Community 37"
Cohesion: 0.16
Nodes (32): ChatRequest, _copy_upload_limited(), CreateNoteRequest, CreateProjectRequest, LLMConfigRequest, LLMConfigResponse, BaseModel, ValueError (+24 more)

### Community 38 - "Community 38"
Cohesion: 0.11
Nodes (29): applyTheme(), bindTimelineScrubbing(), COMMANDS, filteredCommands, fitTimelineToWindow(), formatTimecode(), initTheme(), llmModelSelect (+21 more)

### Community 39 - "Community 39"
Cohesion: 0.10
Nodes (28): list_provider_ids(), list_provider_specs(), list_visible_providers(), _pi_stream(), provider_default_model(), ProviderSpec, LLM provider registry — single source of truth.  Centralises the provider name →, One LLM backend.      All metadata the server, UI, and dispatcher need to work w (+20 more)

### Community 40 - "Community 40"
Cohesion: 0.09
Nodes (31): _env_bool(), _env_int(), _env_str(), get_context_budget_config(), get_overlay_config(), get_visual_verify_config(), Any, Centralised env-var loading for the open_edit server.  v1.5 introduced a new vis (+23 more)

### Community 41 - "Community 41"
Cohesion: 0.12
Nodes (30): find_silence_gaps(), propose_cuts(), Silence cutter skill: propose cuts at silence gaps.  Per phase4-design-revised.m, Find silence intervals >= ``threshold_ms`` in source time.      Returns a list o, Return gap-based cut suggestions for `asset`.      Each suggestion is a dict::, WordAlignment, no_word_split_check(), Check if a cut at [t_start, t_end] splits any word.      A cut splits a word if (+22 more)

### Community 42 - "Community 42"
Cohesion: 0.14
Nodes (29): dispatch_mcp_tool(), _job_to_dict(), mcp_tool_schemas(), Any, Path, Map MCP tool calls onto Open Edit pillar dispatch.  ``project_path`` is injected, Anthropic-shaped schemas for pillars + render helpers., Serialize a tool result for MCP TextContent. (+21 more)

### Community 43 - "Community 43"
Cohesion: 0.11
Nodes (29): _chromium_available(), collect_diagnostics(), _disk_free_bytes(), get_health(), _mlt_available(), System health & diagnostics collection for the open_edit server.  Provides three, Return a redacted system health snapshot. NEVER raises., Return True unless a critical component is catastrophically missing.      Permis (+21 more)

### Community 44 - "Community 44"
Cohesion: 0.14
Nodes (28): cmd_free_form(), cmd_list(), cmd_mcp(), cmd_notes(), cmd_notes_dismiss(), cmd_notes_list(), cmd_render(), cmd_serve() (+20 more)

### Community 45 - "Community 45"
Cohesion: 0.09
Nodes (26): _check_type(), Any, ValueError, Hand-rolled schema validation for Open Edit tool arguments.  Validates tool argu, Raised when tool arguments don't match the schema., Check that ``value`` matches ``expected_type``.      ``number`` accepts both ``i, Validate ``args`` against the schema for ``name``.      Raises ``SchemaValidatio, Return an error dict if validation fails, or None if valid. (+18 more)

### Community 46 - "Community 46"
Cohesion: 0.10
Nodes (29): _clip(), _derive(), _project(), Add clip then move it to a new position, assert new position., Add clip then trim in/out points, assert new in/out., Add clip then slip it, assert result stays within original bounds., Add effect then set keyframe, assert keyframe is stored., Add two clips then add transition between them. (+21 more)

### Community 47 - "Community 47"
Cohesion: 0.08
Nodes (28): Path, Tests for asset streaming in the Open Edit server.  Pins down v1.4 P0-2: a fresh, ``GET /api/projects/{id}`` returns assets whose ``url`` field     points at the, A GET on the asset's ``url`` returns the file with the right     ``Content-Type`, An mp4 asset served via the streaming route has     ``Content-Type: video/mp4``, A Range request returns 206 Partial Content with the right     ``Content-Range``, An unknown asset hash returns 404, not 500 (no exception leak)., An unknown project id returns 404 (not 500). (+20 more)

### Community 48 - "Community 48"
Cohesion: 0.11
Nodes (21): _db_path(), load_project(), make_ir(), _notes_db_path(), _project_root(), Any, list, Path (+13 more)

### Community 49 - "Community 49"
Cohesion: 0.11
Nodes (23): execute_tool(), Run a tool from ``open_edit.agent.tools.<name>``.      The tool signature is ``f, Compatibility shim — see ``open_edit.kernel.tool_executor``., Integration tests for the 4 pillar tools through the dispatch layer., test_edit_project_generate_unknown(), test_edit_project_unknown_operation(), test_query_project_unknown_query(), project_path() (+15 more)

### Community 50 - "Community 50"
Cohesion: 0.09
Nodes (18): build_tool_schemas(), EditProjectArgs, BaseModel, QueryProjectArgs, Pydantic-backed registry of Open Edit pillar tool argument schemas.  Single sour, Return Anthropic-shaped tool schemas generated from the registry., Validate LLM tool-call args against the registered model.      Raises ``ValueErr, RunScriptArgs (+10 more)

### Community 51 - "Community 51"
Cohesion: 0.10
Nodes (27): _pi_binary(), _pi_normalize_event(), Map one pi JSON event to one or more of our StreamEvent dicts.      Pi's event t, _collect(), fake_pi(), fixture, StreamEvent, Tests for the ``pi`` provider in ``open_edit.serve.llm``.  We don't actually spa (+19 more)

### Community 52 - "Community 52"
Cohesion: 0.11
Nodes (13): _ensure_schema(), JobLock, _now_iso(), In-flight job lock backed by the SQLite jobs table.  A single lock for all kinds, Single-slot lock for sandbox runs, renders, and migrations., Add partial unique index for atomic lock acquire (additive migration)., Release locks older than STALE_LOCK_TIMEOUT_SEC., _release_stale_locks() (+5 more)

### Community 53 - "Community 53"
Cohesion: 0.11
Nodes (28): _argv_of(), _make_popen_mock(), Build a minimal RenderSpec-shaped dict for the composition tests., Return the argv list from a mocked subprocess.Popen call., Build a fake Popen instance for the cancellation-aware wrappers., Test 19: subprocess.Popen is called with shell=False (explicit)., Test 20: argv contains '--format mov' (not '--format mp4' or '--transparent')., Test 21: argv contains '-c' (not '--input' which doesn't exist). (+20 more)

### Community 54 - "Community 54"
Cohesion: 0.13
Nodes (20): EffectCatalog, EffectSpec, ParamSpec, BaseModel, Path, Load the effect catalog from a directory of YAML files., In-memory registry of effect specs loaded from YAML., _get_default_catalog() (+12 more)

### Community 55 - "Community 55"
Cohesion: 0.14
Nodes (25): build_server(), main(), parse_args(), Namespace, Path, stdio MCP entry point for Open Edit.  Usage:   open-edit-mcp --project /path/to/, Serve MCP over stdin/stdout for the pinned project., Construct an MCP ``Server`` bound to ``project_path``. (+17 more)

### Community 56 - "Community 56"
Cohesion: 0.15
Nodes (26): _build_render_spec(), _emit(), _emit_error(), _load_timeline(), main(), _make_should_cancel(), Any, Path (+18 more)

### Community 57 - "Community 57"
Cohesion: 0.09
Nodes (26): _mock_stream_chat_with_usage(), StreamEvent, Tests for v1.4 P1-3 cost-update plumbing in ``open_edit.serve.agent``.  The agen, The sidecar lives at ``<project>/.open_edit/cost.json`` —     alongside the conv, Return a stream_chat mock that yields the given usage events     before yielding, When the LLM yields a ``usage`` event, the agent loop must     emit a ``cost_upd, A turn that loops through multiple LLM calls (model calls a     tool, gets the r, After the turn, the sidecar JSON at     ``<project>/.open_edit/cost.json`` must (+18 more)

### Community 58 - "Community 58"
Cohesion: 0.11
Nodes (19): Agent tool: append AddRemotionCompositionOp (and optionally scaffold)., AddRemotionCompositionOp, Add a React Remotion composition that materializes to a CAS clip.      ``entry_p, Remove a Remotion composition by ``composition_uid``., RemoveRemotionCompositionOp, SQLite-backed edit graph store.  One .db file per project. WAL mode for concurre, T1: Conftest fixture sanity check.  The fixture must produce on-disk state that, Path (+11 more)

### Community 59 - "Community 59"
Cohesion: 0.10
Nodes (15): Asset, Content-addressed asset store with ffprobe metadata.  Layout: <assets_dir>/<sha2, fixture, Pytest configuration for open_edit tests., An isolated notes database file under a fresh tmp dir., A project with one asset pre-ingested, suitable for free-form runs (L9).      Se, tmp_notes_db(), tmp_project_with_assets() (+7 more)

### Community 60 - "Community 60"
Cohesion: 0.10
Nodes (25): generate_waveform_inspection_image(), _probe_streams(), Path, Return (has_video, has_audio) for input_path using ffprobe or ffmpeg., Generate dual-panel video frame + audio waveform composite image around cut boun, skipif, Unit tests for waveform cut inspection image generation (visual_verify.py)., Verify hstack layout splits width and produces side-by-side filter. (+17 more)

### Community 61 - "Community 61"
Cohesion: 0.10
Nodes (25): parse_verdict(), Find the first ``VERIFICATION: <X>`` line in ``text`` (case-insensitive).      R, Return deduped, clamped frame timestamps for a video of length     ``duration_s`, sample_frames(), A real LLM response containing ``VERIFICATION: PASS`` extracts as pass., No verdict line → unknown (caller decides what to do; the spec     requires a no, test_no_verdict_line_returns_unknown(), test_parse_verdict_in_message() (+17 more)

### Community 62 - "Community 62"
Cohesion: 0.14
Nodes (18): canonical_json_hash(), Any, Path, Render cache keyed by SHA-256 of canonical JSON of the edit graph., SHA-256 of canonical JSON. Sorted keys, no whitespace, list-ordered., Filesystem-backed render cache, keyed by hash., Copy `source_path` into the cache. Returns the destination path., True if the file exists and is younger than max_age_sec. (+10 more)

### Community 63 - "Community 63"
Cohesion: 0.10
Nodes (24): _is_localhost_websocket(), Validate remote chat connections before ``accept()``.      HTTP middleware does, _websocket_auth_error(), SimpleNamespace, Tests for the v1.4 fast-fail readable-error contract.  Background (P0-1 in v1.4, GET /api/projects/{id} for a freshly-initialised project returns     the empty s, Connecting a WS to an unknown project sends an error event whose     message inc, Regression: an exception raised inside a route handler must NOT     include ``st (+16 more)

### Community 64 - "Community 64"
Cohesion: 0.17
Nodes (25): addAssetToTimeline(), addNoteAtPlayhead(), clearAssetsList(), deleteEdit(), handleFiles(), hideEditDetail(), isProxyStale(), loadProjectState() (+17 more)

### Community 65 - "Community 65"
Cohesion: 0.09
Nodes (24): _mock_execute_tool(), _mock_stream_chat(), patched_ws(), Any, fixture, StreamEvent, Tests for the WebSocket chat endpoint.  Uses FastAPI's ``TestClient.websocket_co, Server sends a `ready` event right after accepting the WS. (+16 more)

### Community 66 - "Community 66"
Cohesion: 0.14
Nodes (22): EncoderBackend, apply_profile_vcodec(), detect_gpu_vcodec(), _ffmpeg(), ffmpeg_video_args(), _probe_encoder(), Video encoder backend selection: GPU (default) or CPU.  Resolves the best availa, Return ``gpu`` or ``cpu`` from explicit request or env default. (+14 more)

### Community 67 - "Community 67"
Cohesion: 0.14
Nodes (21): get_asset_store(), Return the AssetStore rooted at <project>/.open_edit/assets., _allowlist_roots(), ingest_local(), _path_allowed(), Any, Path, pyagent_ingest_local: ingest local media files into the project CAS.  Paths must (+13 more)

### Community 68 - "Community 68"
Cohesion: 0.13
Nodes (23): get_adapter(), Look up an adapter by name. Raises ``KeyError`` on unknown., get_provider_models(), Return the model list for a provider.      For CLI providers, this may shell out, Tests for the v1.7 CLIAdapter interface and registry., R4 fix: every CLIAdapter must have a positive default_timeout_s., Pi has the open_edit TS extension; tools are available., Opencode has no open_edit extension yet (v1.8+). (+15 more)

### Community 69 - "Community 69"
Cohesion: 0.11
Nodes (15): button_cta(), Button template: call-to-action text on a bright background, static., cost_warning(), Cost template: warning-style text on a dark background, mild pulse., hook_fade_text(), Hook template: fade-in text on a colored background.  The render sandbox (W2) ex, Motion graphics templates, one per narrative beat type., mechanism_diagram() (+7 more)

### Community 70 - "Community 70"
Cohesion: 0.16
Nodes (20): _ensure_keys_file_dir(), get_masked_keys_summary(), get_stored_key(), load_all_stored_keys(), mask_key(), Any, Path, v1.8 — Secure Non-Technical BYOK (Bring Your Own Key) Store.  Stores user-entere (+12 more)

### Community 71 - "Community 71"
Cohesion: 0.13
Nodes (13): _has_whisper(), Path, faster-whisper integration for word-level alignment.  Per phase4-design-revised., Resolve Whisper model size from arg or ``OPEN_EDIT_WHISPER_MODEL``., Resolve language override from arg or ``OPEN_EDIT_WHISPER_LANGUAGE``.      Empty, Transcribe an audio/video file to word-level alignment.      ``model_size`` defa, transcribe(), whisper_language() (+5 more)

### Community 72 - "Community 72"
Cohesion: 0.14
Nodes (20): _FakeState, _patch_common(), asyncio, Regression tests for the v1.9 agent-loop stability fixes.  Covers the root cause, The loop must NOT re-call stream_chat after tools complete (the old     bug: sec, The LLM retries the same failing call with identical args; after 3     attempts, A tool returning {"status": "error", ...} (no exception) still     counts as a f, Two trigger_renders in one batch: only the last executes, but the     first stil (+12 more)

### Community 73 - "Community 73"
Cohesion: 0.09
Nodes (21): v1.6: tests for the HTML overlay compositing module.  The module is split into 4, V2: render_overlay_layer.should_cancel must be Callable[[], bool] | None., V2: composite_with_background.should_cancel must be Callable[[], bool] | None., V2: _run_subprocess_with_cancel.should_cancel must be Callable[[], bool] | None., Pinned `node_modules/.bin/hyperframes` exists → it's returned, no warning., Test 24: FileNotFoundError → OverlayRenderError., No pinned binary → bare `npx hyperframes`, WARNING logged with the prescribed me, Test 34: 3 GB estimate → OverlayRenderError (no subprocess spawned). (+13 more)

### Community 74 - "Community 74"
Cohesion: 0.09
Nodes (9): ir_instance(), fixture, Phase 3 Task 4: IR API real implementation (12 methods, parent_id stamped)., H10: the buffer is a SupportsAppend; works with any list-like., Schema errors fail at build time (Pydantic ValidationError)., IR.add_effect must return the op's effect_id, distinct from edit_id.      Regres, test_add_effect_returns_canonical_effect_id(), test_ir_works_with_list_subclass() (+1 more)

### Community 75 - "Community 75"
Cohesion: 0.13
Nodes (18): Default, Error, ExitStatus, Fn, Limits, Command, Result, String (+10 more)

### Community 76 - "Community 76"
Cohesion: 0.10
Nodes (8): dict, _opencode_models_via_cli(), _OpenCodeAdapter, _PiAdapter, v1.7 — CLI adapter interface.  A ``CLIAdapter`` is a thin facade over a single C, Marker subclass; consumers treat as dict[str, Any]., Run ``opencode models`` and return the list of model ids.      Cached for 60s. I, _StreamEvent

### Community 77 - "Community 77"
Cohesion: 0.15
Nodes (20): get_sandbox_backend(), Select the free-form sandbox backend from the environment.      Env contract (``, _allow_tmp_workdir(), _bwrap_fail_proc(), _make_project(), fixture, Pluggable sandbox backend selection + fail-closed behavior.  Covers the refactor, BwrapBackend.run raises SandboxUnavailable when bwrap can't create     its names (+12 more)

### Community 78 - "Community 78"
Cohesion: 0.16
Nodes (18): init_remotion_project(), Any, Path, Agent tool: scaffold a Remotion project under ``.open_edit/remotion/``., ensure_remotion_scaffold(), Path, Frozen Remotion starter copied into each project's `.open_edit/remotion/`., Create the Remotion starter under ``.open_edit/remotion`` if missing. (+10 more)

### Community 79 - "Community 79"
Cohesion: 0.11
Nodes (15): Run free-form Python; return {status, ops, error}., run_python(), Compatibility shim — see ``open_edit.kernel.pillar_tools``., Tests for the pillar tools dispatch functions., test_dispatch_edit_unknown(), test_dispatch_generate_unknown(), test_dispatch_query_unknown(), test_run_python_importable() (+7 more)

### Community 80 - "Community 80"
Cohesion: 0.26
Nodes (17): appendErrorMessage(), appendRenderEvent(), appendSearchResults(), appendTextDelta(), appendToolCard(), appendUserMessage(), completeToolCard(), ensureChatPlaceholderGone() (+9 more)

### Community 81 - "Community 81"
Cohesion: 0.13
Nodes (16): apply_command(), _db_path(), open_store(), Any, Path, Append one validated timeline command and return the new revision., Compatibility shim — see ``open_edit.kernel.edit_graph_service``., project() (+8 more)

### Community 82 - "Community 82"
Cohesion: 0.15
Nodes (16): _extract_token(), _is_localhost(), Request, Response, make_error(), Any, Exception, Unified error envelope for the Open Edit server.  Provides a single, dependency- (+8 more)

### Community 83 - "Community 83"
Cohesion: 0.10
Nodes (19): Tests for the cost badge in the chat UI (v1.4 P1-3).  The cost badge sits next t, Source=pi: render the per-turn + session cost in dollars., Source=computed (anthropic/openai): same dollar-format label     as pi. The sour, Source=unavailable: show the honest "cost n/a" message     instead of a fake $0., The cost badge factory is intentionally focused: it only     reacts to ``cost_up, The chat log's ``handleWsEvent`` must route ``cost_update``     events to the co, When source=pi or source=computed, the badge text contains     a $ glyph. Pinned, Until the first ``cost_update`` event arrives, the badge     should be hidden. T (+11 more)

### Community 84 - "Community 84"
Cohesion: 0.18
Nodes (16): lib_version_supported(), _load_manifest(), parse_header(), Parse `# ir_api_version: X.Y; libs: {...}` headers and check against the allowed, Parse the ir_api_version header from a free-form Python script.      Returns (ve, version_supported(), Phase 3 Task 3: parse_header + version_supported + lib_version_supported., H8: ast.literal_eval rejects unquoted dict keys. (+8 more)

### Community 85 - "Community 85"
Cohesion: 0.19
Nodes (8): AddHtmlOverlayOp, Add an HTML/CSS/JS overlay (e.g. lower-third, title card, caption) that     will, _base_project(), _overlay_op(), An overlay ending at t=12 should push duration_sec to at least 12., If clips end later than overlays, duration_sec reflects the clips., TestAddHtmlOverlayOpValidation, TestDeriveTimelineWithOverlays

### Community 86 - "Community 86"
Cohesion: 0.20
Nodes (17): build_keep_ranges(), compress_silence(), compress_silence_audio(), _concat_ranges(), detect_silences(), extract_audio(), probe_duration(), Path (+9 more)

### Community 87 - "Community 87"
Cohesion: 0.18
Nodes (16): _build_state_summary(), _build_system_prompt(), Return a brief summary of the project state (under 1KB)., Build the system prompt.      Deterministic: the same ``state`` always produces, ProjectState, Full snapshot of a project returned by GET /api/projects/{id}., patched_agent_with_cost(), fixture (+8 more)

### Community 88 - "Community 88"
Cohesion: 0.20
Nodes (17): _map_stop_reason(), parse_opencode_events(), Any, v1.7 — opencode CLI event normalizer.  Reads a sequence of bytes from an ``openc, Map opencode's ``part.tokens`` + ``part.cost`` to our usage shape., Read raw stdout lines from ``opencode run --format json`` and yield     ``Stream, _usage_from_part(), _feed() (+9 more)

### Community 89 - "Community 89"
Cohesion: 0.20
Nodes (17): current_version(), ensure_schema(), _migration_files(), Connection, Path, Lightweight, safe SQLite migration runner for the edit-graph store.  Schema evol, Return the schema version recorded in ``PRAGMA user_version``., Map migration id -> SQL file path, discovered from this directory. (+9 more)

### Community 90 - "Community 90"
Cohesion: 0.11
Nodes (17): Run heavy-compute code in the render sandbox. Returns a RenderResult     (never, run_render(), RenderResult, P9: run_render also validates workdir. A workdir outside the allowed     root re, 5b: render sandbox stderr/stdout is logged server-side but NOT     surfaced in r, I1: missing render binary → RenderResult(ok=False), no exception.      Before th, I1: render binary exits non-zero → RenderResult(ok=False), no exception.      5b, I1: render binary exits 0 but doesn't produce output → RenderResult(ok=False). (+9 more)

### Community 91 - "Community 91"
Cohesion: 0.22
Nodes (16): Canonical hashing of an edit graph for timeline snapshot caching., _cached_done_result(), execute_trigger_render(), _is_error_result(), _payload_hash(), Any, Path, Shared tool execution (Wave 3.2).  The agent loop (``agent.py``) and the TS-exte (+8 more)

### Community 92 - "Community 92"
Cohesion: 0.18
Nodes (16): get_ui_config(), Frontend mode flags (review studio vs full agent UI)., auto_proxy_enabled(), is_review_only(), Review-only server mode (no built-in LLM / chat)., When set, the review UI may enqueue a proxy render after graph changes., True when the UI is a harness-driven review studio (MCP plugin workflow)., client() (+8 more)

### Community 93 - "Community 93"
Cohesion: 0.14
Nodes (17): _prune_render_jobs(), Remove terminal entries older than ``_RENDER_JOB_TTL_S``.      Only entries with, _register_job(), _clear_jobs(), fixture, Tests for the v1.6 render-job registry pruning (P5).  Background: ``_RENDER_JOBS, Every ``_register_job`` write also prunes, so the dict can't     grow without bo, After N renders where each finishes immediately as a terminal     entry, the dic (+9 more)

### Community 94 - "Community 94"
Cohesion: 0.22
Nodes (17): Stream an LLM response as a sequence of :class:`StreamEvent`.      ``messages``, stream_chat(), fake_opencode(), fake_opencode_hang(), asyncio, fixture, MonkeyPatch, Path (+9 more)

### Community 95 - "Community 95"
Cohesion: 0.17
Nodes (15): discover_runtimes(), find_binary_in_expanded_path(), get_expanded_path_env(), Any, v1.8 — Runtime Registry & GUI PATH Expansion.  All provider metadata is defined, Return an expanded PATH string including common CLI install dirs., Search for a binary in PATH + common fallback directories., Specification and status of an LLM runtime.      Fields are derived from the can (+7 more)

### Community 96 - "Community 96"
Cohesion: 0.16
Nodes (17): v1.5: tests for the verification chip in the chat UI.  A small chip near the cha, On a ``verification_started`` event the chip should drop the     ``hidden`` clas, ``outcome=pass`` is the happy path: chip transitions to     ``verified`` (green), ``outcome=uncertain`` and ``outcome=failed`` both mean the visual     check didn, ``outcome=skipped`` is the path where the server itself decided     not to run v, ``outcome=capped`` is the path where the per-turn render cap     was hit. The ch, After a turn finishes, the chip must reset to ``idle`` and     re-hide. Per the, Run ``script_body`` (JS) through the harness and return the     ``(returncode, s (+9 more)

### Community 97 - "Community 97"
Cohesion: 0.17
Nodes (15): generate_visual(), MotionTemplateParams, BaseModel, Path, Motion graphics engine: runs templates to produce video assets.  Per phase4-desi, Parameters consumed by every motion-graphics template.      ``asset_references``, Run a motion-graphics template, ingest the output, emit AddClipOp.      Args:, Phase 4.5 W7: motion graphics templated skill. (+7 more)

### Community 98 - "Community 98"
Cohesion: 0.14
Nodes (15): app_js_path(), harness(), Path, Shared harness for the v1.4 Node-sandbox frontend tests.  The frontend (``open_e, Build a Node script that loads app.js as an ES module into a     stubbed browser, Write ``script`` to a temp file and run it with Node. The script     receives th, The absolute path to the app's entry-point ES module. Resolved     relative to t, run_node_script() (+7 more)

### Community 99 - "Community 99"
Cohesion: 0.21
Nodes (16): fake_pi(), asyncio, fixture, MonkeyPatch, Path, Regression tests for the _stream_pi → _stream_cli refactor (Phase 1).  These tes, The pi adapter from cli_adapter.py has the same name + timeout., Per-project .open_edit/config.toml must override env vars. (+8 more)

### Community 100 - "Community 100"
Cohesion: 0.25
Nodes (14): can_swap(), OperationUnion, Commutativity predicate for reordering operations., Whether two adjacent operations can be safely reordered.      Conservative: when, _refs_clip(), _add(), Tests for commutativity of operations (used by reorder)., test_add_clip_and_remove_different_clips_commute() (+6 more)

### Community 101 - "Community 101"
Cohesion: 0.25
Nodes (15): _is_summary(), prune_images(), Return a new slim view of ``history`` with image blocks stripped and     verific, Return a copy of ``result`` with ``verification.frames`` removed.      Frame dat, _strip_verification_frames(), _make_tool_result_message(), _make_verification_result(), Tests for prune_images and _build_tool_result_message base64 dedup. (+7 more)

### Community 102 - "Community 102"
Cohesion: 0.20
Nodes (15): client_and_project(), asyncio, fixture, MonkeyPatch, Path, TestClient, Empirical verification test suite written by Challenger 2.  Covers: - GET /api/h, Test stream_chat yields structured error after retries exhausted (3 attempts tot (+7 more)

### Community 104 - "Community 104"
Cohesion: 0.17
Nodes (13): A Remotion React composition pending materialization to a CAS clip.      Produce, RemotionComposition, fixture, MonkeyPatch, Path, skipif, Golden Remotion → materialize → emit / proxy path (fake Remotion CLI)., Full proxy path: Remotion materialize then melt. (+5 more)

### Community 105 - "Community 105"
Cohesion: 0.25
Nodes (11): BaseHTTPMiddleware, Fail-safe bearer-token auth with a localhost bypass.      Auth is only enforced, TokenAuthMiddleware, _ok_call_next(), Request, Response, Tests for /health, /diagnostics, and token auth middleware., _remote_request() (+3 more)

### Community 106 - "Community 106"
Cohesion: 0.22
Nodes (14): boot(), refreshProjects(), renderProjectSelect(), selectProject(), clearChatLog(), createChatStatus(), createCostBadge(), createVerifyChip() (+6 more)

### Community 107 - "Community 107"
Cohesion: 0.24
Nodes (12): openNotesModal(), openSettingsModal(), assetIcon(), openAssetPreview(), renderAssets(), fmtBytes(), fmtDuration(), fmtTime() (+4 more)

### Community 108 - "Community 108"
Cohesion: 0.21
Nodes (13): format_timestamp(), pack_transcript(), Format word alignments into silence-aware, speaker-grouped Markdown string., Format seconds into timestamp string MM:SS.ms (or HH:MM:SS.ms if >= 1hr)., Path, Unit tests for phrase-packed transcription formatting, tool handler, and registr, test_format_timestamp(), test_get_transcript_packed_tool() (+5 more)

### Community 109 - "Community 109"
Cohesion: 0.27
Nodes (12): load_conversation(), Load a conversation from disk. Returns ``[]`` if it doesn't exist., _project_with_jsonl(), Path, Tests for conversation sync between JSONL and pi session., Simulate mid-turn crash: save after each tool_result, crash, restart., Each line must be valid JSON., test_append_and_load_roundtrip() (+4 more)

### Community 110 - "Community 110"
Cohesion: 0.24
Nodes (11): cap_tool_result(), Any, Cap oversized tool results before they enter conversation history.  Called from, Return a copy of ``result`` with oversized fields truncated.      * Truncates ``, Tests for the result_capper module., test_error_field_truncated(), test_long_list_capped(), test_oversized_stdout_truncated() (+3 more)

### Community 111 - "Community 111"
Cohesion: 0.23
Nodes (13): autoGrowInput(), bindEvents(), cancelTurn(), copyPlayheadTimecode(), executeCmd(), filterCmdList(), handleCmdKeydown(), handleSend() (+5 more)

### Community 112 - "Community 112"
Cohesion: 0.15
Nodes (11): Scenario Evaluation Suite for Open Edit — Phase 7.  Tests the IR/apply layer aga, Add clip+effect then remove effect, assert effect is gone., Add clip to track1, add clip to track2, verify order-independent., Add clip, replace its source asset, assert new hash., Overlay ending at t=20 should push duration to at least 20., Run all scenarios. Return (passed, failed)., run_all(), scenario_overlay_duration_affects_total() (+3 more)

### Community 113 - "Community 113"
Cohesion: 0.26
Nodes (11): CompletedProcess, Path, End-to-end CLI tests for open_edit init/list/summary/undo., `open_edit render` runs without error on an empty project (early return)., Regression: `open_edit notes` (no subcommand) used to crash with     NameError b, _run(), test_init_ingests_videos(), test_list_shows_no_ops_initially() (+3 more)

### Community 114 - "Community 114"
Cohesion: 0.19
Nodes (12): _make_buffer(), Phase 4 Task 1: originating_note_id on Operation + IR API + sandbox_bridge., Existing fixtures that don't set the field must still serialize/deserialize., EditGraphStore reads/writes the payload JSON; originating_note_id is preserved., test_edit_graph_store_round_trip(), test_ir_add_clip_default_none(), test_ir_add_clip_stamps_originating_note_id(), test_ir_add_effect_stamps() (+4 more)

### Community 115 - "Community 115"
Cohesion: 0.26
Nodes (12): client_and_project(), fixture, MonkeyPatch, Path, TestClient, Tests for the GET/PUT /api/projects/{id}/llm-config REST routes., Antigravity is a valid provider — the adapter is registered., test_get_llm_config_returns_current_config() (+4 more)

### Community 116 - "Community 116"
Cohesion: 0.21
Nodes (10): ProjectPathError, Path, ValueError, Project path resolution for the local MCP server., Resolve and validate the project directory for MCP tool dispatch.      Preferenc, Raised when the MCP server cannot bind to a valid Open Edit project., resolve_project_path(), __getattr__() (+2 more)

### Community 117 - "Community 117"
Cohesion: 0.26
Nodes (9): profile_to_mlt_args(), Look up a profile by name. Raises KeyError if not found., Convert a profile to melt consumer args., select_profile(), Tests for render profile selection and MLT arg generation., test_profile_to_mlt_args_includes_aspect_and_colorspace(), test_profile_to_mlt_args_includes_codecs(), test_select_profile_returns_named_profile() (+1 more)

### Community 118 - "Community 118"
Cohesion: 0.21
Nodes (11): build_failure_tool_result(), _format(), log_event(), Any, v1.5 visual verification module.  Pure (or near-pure) functions for the post-ren, Spec §4 failure shapes: no ``verification`` block, just an ``error`` key., Emit a single structured log line to stderr via the module logger.      Format:, When the underlying render fails, build a tool result that says so —     no `ver (+3 more)

### Community 119 - "Community 119"
Cohesion: 0.17
Nodes (11): Tests for the frontend chat-status indicator (v1.4 P1-2).  The chat-status indic, The user-visible label for ``tool_running`` must include the tool     name (e.g., Per the brief, the indicator "clears within one frame of ``DONE``     or ``error, A second ``send()`` while the indicator is still showing the     previous turn m, ``window.OpenEdit.__testHooks.createChatStatus`` must exist so     tests can dri, A complete turn walks the indicator through every state and ends     back at idl, test_chat_status_error_then_done_clears(), test_chat_status_full_turn_lifecycle() (+3 more)

### Community 120 - "Community 120"
Cohesion: 0.17
Nodes (11): Frontend tests for the v1.4 P1-1 search-assets results panel.  When the assistan, ``window.OpenEdit.__testHooks.appendSearchResults`` must exist so     tests can, The panel must produce one card per result, with the license     badge and "Add, Each card must surface the license string verbatim so the user     knows the ter, When the tool returns ``{error: "..."}``, the panel must show     the error (not, Clicking the "Add to project" button must trigger an     ``import_asset`` chat m, test_append_search_results_add_button_fires_import(), test_append_search_results_is_exposed_on_test_hooks() (+3 more)

### Community 121 - "Community 121"
Cohesion: 0.27
Nodes (9): list_assets(), Any, pyagent_list_assets: list all ingested assets in the project.  Replaces the phan, Return all ingested assets for the project.      Scans ``<project>/.open_edit/as, Tests for the list_assets tool (Wave 1.2)., test_list_assets_no_assets_dir_is_empty(), test_list_assets_returns_empty_for_empty_project(), test_list_assets_returns_ingested_assets() (+1 more)

### Community 122 - "Community 122"
Cohesion: 0.18
Nodes (8): Pydantic 2.13.4 compatibility shim.  `OperationUnion = Annotated[Union[...], Fie, Tests for the hand-constructed 11-clip / 10-transition golden fixture., The hand-constructed edit graph is a valid Project., Each transition's clip_a_id and clip_b_id must be a real clip_id., Deriving the timeline from the edit graph produces a Timeline with     11 clips, test_golden_edit_graph_loads(), test_golden_expected_timeline_matches_derive(), test_golden_transitions_references_valid_clips()

### Community 123 - "Community 123"
Cohesion: 0.18
Nodes (8): absEntry, absOut, absRoot, compositionId, output, projectRoot, propsFile, result

### Community 124 - "Community 124"
Cohesion: 0.44
Nodes (10): apply_cgroup_limits(), apply_cgroup_limits_at(), apply_cgroup_limits_at_returns_error_for_nonexistent_path(), apply_cgroup_limits_at_writes_three_files_when_dir_exists(), apply_cgroup_limits_returns_error_for_nonexistent_default_dir(), apply_rlimits(), Limits, Path (+2 more)

### Community 126 - "Community 126"
Cohesion: 0.20
Nodes (10): cmd_init(), projects_root_tmp(), fixture, If the user runs ``open_edit init <some-other-path>`` and the     target is NOT, If the user does the right thing (``init <root>/<proj>``), the     CLI does NOT, Point OPEN_EDIT_PROJECTS_ROOT at a fresh empty dir., A real, fully-initialised project under projects_root_tmp.      Returns (project, seeded_project() (+2 more)

### Community 127 - "Community 127"
Cohesion: 0.38
Nodes (9): Return timeline-level errors (empty list = valid).      Detects overlapping clip, validate_timeline(), _clip(), _overlapping_project(), test_derive_timeline_lenient_loads_overlap(), test_derive_timeline_strict_raises_on_overlap(), test_validate_timeline_clean(), test_validate_timeline_detects_nonpositive_duration() (+1 more)

### Community 128 - "Community 128"
Cohesion: 0.24
Nodes (9): add_serve_subparser(), main(), Any, Namespace, Patch for ``open_edit/cli.py`` — add the ``serve`` subcommand.  This file is NOT, A minimal CLI that ONLY wires up the ``serve`` subcommand.      Useful for testi, Register the ``serve`` subcommand on an argparse subparsers object.      Usage i, Entry point for ``open_edit serve``.      Imports uvicorn lazily so users who ne (+1 more)

### Community 129 - "Community 129"
Cohesion: 0.29
Nodes (9): _coerce_event(), Tests for the StreamEvent contract (Wave 3.3)., StreamEvent must be importable and annotated — not just a docstring., A provider emitting a new event type should not crash the agent loop., test_coerce_event_fills_missing_text_with_empty_string(), test_coerce_event_handles_unknown_type_gracefully(), test_coerce_event_passes_through_valid_text_delta(), test_coerce_event_requires_type_field() (+1 more)

### Community 130 - "Community 130"
Cohesion: 0.20
Nodes (4): OPEN_EDIT_PKG, REAL_DIR, REAL_FILE, ToolDef

### Community 131 - "Community 131"
Cohesion: 0.24
Nodes (10): encode_jpeg(), Extract a single frame from ``input_path`` to ``output_path`` as JPEG,     downs, Subprocess.run is called with shell=False (the default — explicit     test becau, If the encoded JPEG exceeds max_image_bytes, the long-edge limit     is reduced, Write a 1×1 RGB PNG so the test doesn't need real media., encode_jpeg must scale so the long edge is <= max_edge_px, no distortion., test_payload_size_caps_downscale(), test_preserves_aspect_ratio_when_downscaling() (+2 more)

### Community 132 - "Community 132"
Cohesion: 0.38
Nodes (9): bwrap_unavailable_reason(), e2e_network_blocked(), e2e_parent_id_stamped(), e2e_python_runs_and_writes_ops(), e2e_python_version_mismatch(), e2e_source_ro_blocks_writes(), e2e_timeout_kills_runaway(), Command (+1 more)

### Community 133 - "Community 133"
Cohesion: 0.20
Nodes (6): Fake Popen that stays alive until kill() is called., Cancellation during the render calls kill() and raises OverlayRenderError., Cancellation during ffmpeg calls kill() and raises OverlayRenderError., _SlowPopen, test_composite_with_background_cancellation_kills_subprocess(), test_render_overlay_layer_cancellation_kills_subprocess()

### Community 134 - "Community 134"
Cohesion: 0.22
Nodes (8): description, main, name, private, scripts, check, type, version

### Community 135 - "Community 135"
Cohesion: 0.28
Nodes (9): fetchLLMConfig(), loadLLMConfig(), populateModelDropdown(), populateProviderDropdown(), putLLMConfigRequest(), refreshSendGate(), saveLLMConfig(), saveSettingsKeys() (+1 more)

### Community 136 - "Community 136"
Cohesion: 0.33
Nodes (9): model_capability(), Return the multimodal / image capability of a model.      Never raises — unknown, Path, test_capability_dict_includes_constraints(), test_capability_for_minimax_m2_7_omits_image(), test_capability_for_minimax_m3_includes_image(), test_capability_for_unknown_model_returns_unknown(), test_model_capability_returns_dict() (+1 more)

### Community 139 - "Community 139"
Cohesion: 0.25
Nodes (8): build_no_change_tool_result(), project_state_hash(), Spec §4 no-change path: previous render reused, no sampling, no frames., Return sha256 of the canonical project state.      Hash inputs (per spec §2.3):, Same edit graph + same render_id + same render_mode → same hash.     Different e, If project_state_hash matches the last successful render, return a     no_change, test_no_change_render_skips_re_render(), test_no_change_render_skips_sampling()

### Community 140 - "Community 140"
Cohesion: 0.25
Nodes (8): build_verification_tool_result(), Build the structured ``trigger_render`` tool result with verification block., _verification_prompt(), Frames go inside the verification block of the tool result, NOT     in a synthet, When mode=proxy, the prompt must include the proxy-disclaimer paragraph     (ign, test_message_construction_uses_tool_result_blocks(), test_text_only_model_returns_text_only_tool_result(), test_verification_prompt_mentions_proxy_disclaimer()

### Community 141 - "Community 141"
Cohesion: 0.25
Nodes (8): parametrize, asyncio, When ``OPEN_EDIT_LLM_API_KEY`` is unset, ``stream_chat`` emits a     single ``er, Same as the anthropic test, but for the OpenAI provider path.      The two failu, An unrecognised ``OPEN_EDIT_LLM_PROVIDER`` value falls back to     the default (, test_llm_stream_anthropic_surfaces_missing_api_key(), test_llm_stream_openai_surfaces_clean_error(), test_llm_stream_unknown_provider_falls_back_with_warning()

### Community 142 - "Community 142"
Cohesion: 0.54
Nodes (7): PathBuf, Args, build_bwrap_cmd(), in_sandbox_path(), main(), Command, Result

### Community 143 - "Community 143"
Cohesion: 0.25
Nodes (5): Tests for sandbox header auto-injection and run_script., Code with existing header should pass through unchanged., test_header_auto_inject_missing(), test_header_auto_inject_present(), test_run_python_importable()

### Community 144 - "Community 144"
Cohesion: 0.25
Nodes (7): Tests for the v1.4 P2 loading state on the asset list.  The brief: "Asset list a, While ``api.getProjectState`` is in flight, the assets list     must show a load, When ``getProjectState`` fails, the assets list should not be     stuck on a loa, When the user switches projects, the assets list must NOT     keep showing the o, test_load_project_state_clears_loading_marker_on_error(), test_load_project_state_shows_loading_marker_during_fetch(), test_project_switch_shows_loading_state_not_stale_data()

### Community 146 - "Community 146"
Cohesion: 0.29
Nodes (3): Verify the strace observation fixtures are present and parseable., Each strace file should list at least 5 distinct syscalls., test_strace_files_contain_real_syscalls()

### Community 147 - "Community 147"
Cohesion: 0.29
Nodes (7): ffprobe_available(), projects_root_tmp(), fixture, True iff ``ffprobe`` is on PATH. Mirrors the pattern in     ``test_cli.py`` / ``, Point ``OPEN_EDIT_PROJECTS_ROOT`` at a fresh empty dir., A real, fully-initialised project under ``projects_root_tmp``.      Runs ``open_, seeded_project()

### Community 148 - "Community 148"
Cohesion: 0.40
Nodes (5): H5: resolve at call time, not at module import.      Order matches the install c, _resolve_render_binary(), Phase 4.5 W2: render sandbox Python wrapper., The binary is in one of the known locations., test_resolve_render_binary()

### Community 149 - "Community 149"
Cohesion: 0.53
Nodes (4): current_user_process_count(), relative_limit_is_baseline_plus_headroom(), relative_nproc_limit(), relative_nproc_limit_with()

### Community 151 - "Community 151"
Cohesion: 0.33
Nodes (5): Test the v1.4 P2 ES module structure is intact.  The brief: "Add a Node-sandbox, The entry point imports from each sibling module (state,     dom, api, assets, c, The entry-point ES module loads cleanly and exposes the     full ``__testHooks``, test_module_dependencies_resolve(), test_module_loads_and_exposes_test_hooks()

### Community 152 - "Community 152"
Cohesion: 0.40
Nodes (5): list_adapters(), Return the names of all registered adapters (sorted)., _config_summary(), Return a redacted subset of server config. NEVER includes secrets., test_list_adapters_includes_all_providers()

### Community 153 - "Community 153"
Cohesion: 0.40
Nodes (4): is_verify_disabled(), Path, Per-project metadata accessors for the open_edit server.  v1.5 added the ``verif, Return True if the project's ``verify_disabled`` flag is set.      Reads from th

### Community 154 - "Community 154"
Cohesion: 0.50
Nodes (3): compute_keep(), Takeover: build ordered, silence-trimmed timeline via the IR API.  No direct DB, silence_intervals()

### Community 155 - "Community 155"
Cohesion: 0.50
Nodes (4): P9: resolve a caller-supplied workdir.      The AI may operate on any directory;, _validate_workdir(), P9 (loosened): a workdir that is a real project (has edit_graph.db)     is accep, test_validate_workdir_accepts_real_project_outside_root()

### Community 156 - "Community 156"
Cohesion: 0.50
Nodes (3): _load_music_library(), pyagent_select_music: returns music track ops for narrative segments.  Per phase, Load music library from a JSON file; empty list if not provided.

### Community 157 - "Community 157"
Cohesion: 0.33
Nodes (4): Test 18: template not found in either dir raises OverlayRenderError., Test 38: returns the composited MP4 path on success., test_render_composited_returns_final_path_on_success(), test_template_not_found_raises_overlay_render_error()

### Community 158 - "Community 158"
Cohesion: 0.67
Nodes (3): asyncio, Verify that a single JSON line > 2MB does not raise LimitOverrunError., test_huge_line_stream_no_limit_overrun()

### Community 159 - "Community 159"
Cohesion: 0.50
Nodes (3): Test that GET /api/projects/{id} includes timeline_full., An existing project should return timeline_full with tracks/clips., test_project_state_includes_timeline_full()

### Community 160 - "Community 160"
Cohesion: 0.67
Nodes (3): project_with_remotion(), fixture, MonkeyPatch

### Community 161 - "Community 161"
Cohesion: 0.67
Nodes (3): _allow_tmp_workdir(), fixture, P9: permit workdirs under the test's tmp_path by default.      Most tests use `t

### Community 162 - "Community 162"
Cohesion: 0.67
Nodes (3): asyncio, V1: ``_run_trigger_render`` with mode='overlay' must not raise     ``RuntimeErro, test_run_trigger_render_overlay_inside_running_loop()

## Knowledge Gaps
- **28 isolated node(s):** `projectRoot`, `compositionId`, `propsFile`, `output`, `absRoot` (+23 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **35 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `EditGraphStore` connect `Community 11` to `Community 0`, `Community 1`, `Community 2`, `Community 3`, `Community 4`, `Community 6`, `Community 9`, `Community 139`, `Community 12`, `Community 13`, `Community 14`, `Community 15`, `Community 16`, `Community 18`, `Community 19`, `Community 22`, `Community 153`, `Community 154`, `Community 27`, `Community 28`, `Community 29`, `Community 30`, `Community 31`, `Community 160`, `Community 33`, `Community 37`, `Community 42`, `Community 44`, `Community 48`, `Community 49`, `Community 52`, `Community 56`, `Community 58`, `Community 59`, `Community 61`, `Community 77`, `Community 79`, `Community 81`, `Community 87`, `Community 91`, `Community 103`, `Community 104`, `Community 105`, `Community 114`, `Community 118`, `Community 125`, `Community 126`?**
  _High betweenness centrality (0.265) - this node is a cross-community bridge._
- **Why does `Project` connect `Community 0` to `Community 1`, `Community 3`, `Community 9`, `Community 12`, `Community 13`, `Community 14`, `Community 15`, `Community 16`, `Community 22`, `Community 154`, `Community 27`, `Community 35`, `Community 44`, `Community 46`, `Community 48`, `Community 56`, `Community 58`, `Community 59`, `Community 85`, `Community 87`, `Community 104`, `Community 112`, `Community 114`, `Community 122`, `Community 127`?**
  _High betweenness centrality (0.065) - this node is a cross-community bridge._
- **Why does `Timeline` connect `Community 1` to `Community 0`, `Community 3`, `Community 133`, `Community 15`, `Community 18`, `Community 20`, `Community 150`, `Community 23`, `Community 25`, `Community 27`, `Community 162`, `Community 46`, `Community 56`, `Community 58`, `Community 73`, `Community 85`, `Community 104`, `Community 112`, `Community 127`?**
  _High betweenness centrality (0.058) - this node is a cross-community bridge._
- **Are the 47 inferred relationships involving `EditGraphStore` (e.g. with `BwrapBackend` and `DevSubprocessBackend`) actually correct?**
  _`EditGraphStore` has 47 INFERRED edges - model-reasoned connections that need verification._
- **Are the 30 inferred relationships involving `AddClipOp` (e.g. with `BwrapBackend` and `DevSubprocessBackend`) actually correct?**
  _`AddClipOp` has 30 INFERRED edges - model-reasoned connections that need verification._
- **Are the 18 inferred relationships involving `Timeline` (e.g. with `ApplyError` and `EmitterConfig`) actually correct?**
  _`Timeline` has 18 INFERRED edges - model-reasoned connections that need verification._
- **Are the 37 inferred relationships involving `Project` (e.g. with `BwrapBackend` and `DevSubprocessBackend`) actually correct?**
  _`Project` has 37 INFERRED edges - model-reasoned connections that need verification._