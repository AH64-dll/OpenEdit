# Graph Report - .  (2026-08-04)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 3747 nodes · 7190 edges · 269 communities (205 shown, 64 thin omitted)
- Extraction: 86% EXTRACTED · 14% INFERRED · 0% AMBIGUOUS · INFERRED: 995 edges (avg confidence: 0.66)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `65eef8d5`
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
- Community 171
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
- Community 192
- Community 193
- Community 194
- Community 195
- Community 196
- Community 197
- Community 198
- Community 199
- Community 200
- Community 201
- Community 202
- Community 203
- Community 204
- Community 205
- Community 206
- Community 207
- Community 208
- Community 209
- Community 210
- Community 211
- Community 212
- Community 213
- Community 214
- Community 215
- Community 216
- Community 217
- Community 218
- Community 219
- Community 220
- Community 221
- Community 222
- Community 223
- Community 224
- Community 225
- Community 226
- Community 227
- Community 228
- Community 229
- Community 230
- Community 231
- Community 232
- Community 233
- Community 234
- Community 235
- Community 236
- Community 237
- Community 238
- Community 239
- Community 240
- Community 241
- Community 242
- Community 243
- Community 244
- Community 245
- Community 246
- Community 247
- Community 248
- Community 249
- Community 250
- Community 251
- Community 252
- Community 253
- Community 254
- Community 255
- Community 256
- Community 257
- Community 258
- Community 259
- Community 260
- Community 261
- Community 262
- Community 263

## God Nodes (most connected - your core abstractions)
1. `EditGraphStore` - 99 edges
2. `Timeline` - 83 edges
3. `IR` - 62 edges
4. `RenderProfile` - 60 edges
5. `Operation` - 51 edges
6. `PreviewChunkCache` - 49 edges
7. `new_id()` - 46 edges
8. `render_project()` - 44 edges
9. `Project` - 38 edges
10. `AssetStore` - 37 edges

## Surprising Connections (you probably didn't know these)
- `run_free_form_code()` --calls--> `ApplyError`  [INFERRED]
  agent/free_form.py → ir/apply_common.py
- `run_free_form()` --calls--> `EditGraphStore`  [INFERRED]
  agent/sandbox/bridge.py → storage/edit_graph.py
- `run_free_form()` --calls--> `JobLock`  [INFERRED]
  agent/sandbox/bridge.py → storage/job_lock.py
- `cmd_free_form()` --calls--> `run_free_form()`  [INFERRED]
  cli.py → agent/sandbox/bridge.py
- `_FlushingBuffer` --uses--> `Asset`  [INFERRED]
  agent/sandbox/staging.py → ir/types.py

## Import Cycles
- None detected.

## Communities (269 total, 64 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.07
Nodes (59): cache_max_bytes(), cache_ttl_sec(), canonical_json_hash(), _file_hash(), parse_cache_max_bytes(), Any, Path, Filesystem-backed render cache, keyed by the edit-graph hash.  Single hash autho (+51 more)

### Community 1 - "Community 1"
Cohesion: 0.05
Nodes (30): Any, Adapts an EditGraphStore to the IR's SupportsAppend protocol.      EditGraphStor, _StoreBuffer, EditGraphStore, Any, Connection, OperationUnion, Path (+22 more)

### Community 2 - "Community 2"
Cohesion: 0.07
Nodes (34): JobStatus, public_job(), Connection, Path, Row, ValueError, Durable render scheduling and subprocess lifecycle management.  The service is d, Mark jobs interrupted by a prior service process as orphaned. (+26 more)

### Community 3 - "Community 3"
Cohesion: 0.07
Nodes (53): _lifespan(), asset_stream_url(), _asset_to_info(), AssetInfo, create_project(), EffectInfo, get_project_state(), _initialise_project() (+45 more)

### Community 4 - "Community 4"
Cohesion: 0.06
Nodes (48): _build_render_spec(), _extract_output_path(), _load_timeline(), make_should_cancel(), _probe_duration(), Any, Path, Kernel-side overlay render trigger.  This module hosts the ``trigger_render`` to (+40 more)

### Community 5 - "Community 5"
Cohesion: 0.08
Nodes (31): FrameEngine, _bounded_text(), build_frame_server_command(), frame_engine_mode(), frame_engine_status(), FrameProtocolError, FramePullClient, FramePullUnavailableError (+23 more)

### Community 6 - "Community 6"
Cohesion: 0.07
Nodes (48): put, list_visible_providers(), Non-hidden providers, sorted by name.      This is the list shown in the UI drop, auto_preview_enabled(), auto_proxy_enabled(), is_review_only(), preview_chunks_enabled(), Review-only server mode (no built-in LLM / chat). (+40 more)

### Community 7 - "Community 7"
Cohesion: 0.09
Nodes (23): _file_hash(), _mime_for(), _normalise_suffix(), preview_cache_max_age_sec(), preview_cache_max_bytes(), preview_cache_min_free_bytes(), PreviewChunkCache, Any (+15 more)

### Community 8 - "Community 8"
Cohesion: 0.09
Nodes (48): _cache_get(), _cache_key(), _cache_put(), _cache_stale(), _call_provider(), _endpoint_for_error(), _freesound_api_key(), _freesound_attribution_required() (+40 more)

### Community 9 - "Community 9"
Cohesion: 0.10
Nodes (47): OperationPlane, _chunk_plane_key(), classify_operation_planes(), _clip_interval(), _clip_intervals(), _clip_planes(), _composition_interval(), compute_chunk_fingerprints() (+39 more)

### Community 10 - "Community 10"
Cohesion: 0.07
Nodes (42): _bounded_timeout(), _is_timeout(), _normalize_policy(), _policy_skipped_check(), BaseModel, Path, QCMode, QCCheck (+34 more)

### Community 11 - "Community 11"
Cohesion: 0.11
Nodes (41): apply_operation(), _apply_normalize_audio(), _apply_set_audio_gain(), Audio operations: gain and normalize. Pure functions., Add a 'volume' effect tagged with the target_dbfs to the target.      Without a, _apply_change_clip_speed(), _apply_replace_clip_source(), _apply_ripple_delete_clip() (+33 more)

### Community 12 - "Community 12"
Cohesion: 0.07
Nodes (43): HtmlOverlay, A rendered HTML/CSS/JS overlay composited on top of the video track.      Produc, PathLike, _assign_tracks(), _clip_id(), composite_with_background(), _disk_footprint_check(), _estimate_overlay_size_mb() (+35 more)

### Community 13 - "Community 13"
Cohesion: 0.10
Nodes (42): BaseException, Event, Clip, BaseModel, A Remotion React composition pending materialization to a CAS clip.      Produce, RemotionComposition, Track, PreviewVideoRenderer (+34 more)

### Community 14 - "Community 14"
Cohesion: 0.16
Nodes (42): Protocol, Anything with a single-arg `append` (list, _FlushingBuffer, ...)., SupportsAppend, AddClipOp, AddRemotionCompositionOp, AddTransitionOp, ChangeClipSpeedOp, FreeFormCodeOp (+34 more)

### Community 15 - "Community 15"
Cohesion: 0.07
Nodes (24): now_iso8601(), Return the current UTC time as an ISO 8601 string., CommandStore, Path, SQLite-backed command idempotency store.  Tracks tool commands keyed by command_, SQLite store for command idempotency records., Record a command for idempotency. No-op if command_id exists., Return True if a command with the given id has been recorded. (+16 more)

### Community 16 - "Community 16"
Cohesion: 0.16
Nodes (9): IR, Any, Free-form Python IR API. Each method appends one Pydantic op to the buffer., Append AddRemotionCompositionOp; return composition_uid., Append AddHtmlOverlayOp; return overlay_id., Caller-supplied value wins; else fall back to the IR-level value., Append AddClipOp; return generated clip_id., new_id() (+1 more)

### Community 17 - "Community 17"
Cohesion: 0.11
Nodes (36): _check_graph(), _chunk_size(), _clear_job_id(), _content_fingerprint(), _fingerprint_inputs(), _graph_identity(), _job_temp_dir(), _load_job_params() (+28 more)

### Community 18 - "Community 18"
Cohesion: 0.08
Nodes (31): ProjectPathError, Path, ValueError, Project path resolution for the local MCP server., Resolve and validate the project directory for MCP tool dispatch.      Preferenc, Raised when the MCP server cannot bind to a valid Open Edit project., resolve_project_path(), __getattr__() (+23 more)

### Community 19 - "Community 19"
Cohesion: 0.10
Nodes (30): FastAPI, patch, FastAPI app for the Open Edit server.  Routes ------ - ``GET  /api/projects``, Asset streaming routes (v1.4 P0-2)., delete_op(), post_timeline_command(), BaseModel, delete (+22 more)

### Community 20 - "Community 20"
Cohesion: 0.13
Nodes (26): add_marker(), pyagent_add_marker: agent-initiated flag, writes to NotesStore with source=agent, Append a ReviewNote with source=agent at the given timestamp., cmd_notes_add(), `open_edit notes add` — append a note to a project (M1)., CreateNoteRequest, CreateProjectRequest, post_project_note() (+18 more)

### Community 21 - "Community 21"
Cohesion: 0.07
Nodes (21): Logger, LogRecord, bind_context(), ContextFilter, CorrelationIdMiddleware, get_context(), get_logger(), JsonFormatter (+13 more)

### Community 22 - "Community 22"
Cohesion: 0.13
Nodes (33): _blend(), _call_detector(), collect_source_baseline(), _detector_result(), _hash_file(), _map_span(), _merge_repair_spans(), _overlaps_any() (+25 more)

### Community 23 - "Community 23"
Cohesion: 0.15
Nodes (17): AssetProxyJobStatus, _asset_advisory_lock(), AssetProxyJob, AssetProxyJobService, _project_root(), public_job(), Connection, Path (+9 more)

### Community 24 - "Community 24"
Cohesion: 0.13
Nodes (32): cmd_free_form(), cmd_init(), cmd_list(), cmd_mcp(), cmd_notes(), cmd_notes_dismiss(), cmd_notes_list(), cmd_preview_chunks() (+24 more)

### Community 25 - "Community 25"
Cohesion: 0.09
Nodes (30): get_adapter(), Look up an adapter by name. Raises ``KeyError`` on unknown., Any, Generic subprocess driver for CLI providers (pi, opencode, antigravity, jcode) +, Generic subprocess driver for any CLIAdapter (pi, opencode, ...).      Builds th, Pi provider — delegates to _stream_cli with the PiAdapter.      After _stream_cl, _stream_cli(), _stream_pi() (+22 more)

### Community 26 - "Community 26"
Cohesion: 0.10
Nodes (26): OSError, PreviewStatus, PreviewCacheError, A preview write was rejected before it could publish an artifact., _artifact_is_usable(), _artifact_path(), _initial_plane_state(), _load_snapshot() (+18 more)

### Community 27 - "Community 27"
Cohesion: 0.15
Nodes (27): boot(), cancelTurn(), sendText(), setChatEnabled(), appendErrorMessage(), appendRenderEvent(), appendTextDelta(), appendToolCard() (+19 more)

### Community 28 - "Community 28"
Cohesion: 0.14
Nodes (18): Asset, SourceProxyStatus, AssetStore, _hash_file(), list_assets_from_disk(), _probe_media(), Path, Content-addressed asset store with ffprobe metadata.  Layout: <assets_dir>/<sha2 (+10 more)

### Community 29 - "Community 29"
Cohesion: 0.09
Nodes (21): list_adapters(), _opencode_models_via_cli(), _OpenCodeAdapter, _pi_binary(), _pi_extension_path(), _PiAdapter, v1.7 — CLI adapter interface.  A ``CLIAdapter`` is a thin facade over a single C, Default: <open_edit>/serve/pi_extension/extension.ts (+13 more)

### Community 30 - "Community 30"
Cohesion: 0.15
Nodes (24): Public entry point: ``stream_chat`` (async generator) + CLI conversation seriali, Stream an LLM response as a sequence of :class:`StreamEvent`.      ``messages``, stream_chat(), TypedDict, StreamEvent contract — the one event shape every provider yields., One event yielded by :func:`stream_chat`.      Variants (the ``type`` field disc, StreamEvent, Async streaming LLM client for the Open Edit server.  Three backends supported v (+16 more)

### Community 31 - "Community 31"
Cohesion: 0.11
Nodes (25): _alpha_vcodec(), _default_remotion_concurrency(), probe_alpha_capability(), Any, Path, Popen, Remotion subprocess execution: command building, lifecycle, and codec mapping., Resolve ``auto`` to a verified alpha codec, never a guess. (+17 more)

### Community 32 - "Community 32"
Cohesion: 0.15
Nodes (25): _cache_result_path(), _http_download(), import_asset(), _import_manifest_path(), _is_allowed_source_url(), _is_private_or_local_host(), _lookup_result(), _open_url() (+17 more)

### Community 33 - "Community 33"
Cohesion: 0.13
Nodes (25): EncoderSpec, Quality args for one encoder, rendered in both arg dialects.      ``melt_args``, PreviewVideoRequest, TypedDict, One frame-aligned preview range and its rendering context., OverlayClip, _bake_chunk(), _chunk_status() (+17 more)

### Community 34 - "Community 34"
Cohesion: 0.12
Nodes (25): Any, Path, CLI-owned turns (pi / opencode / antigravity / jcode).  CLI providers run a COMP, Run one turn against a provider that owns its agent loop., _run_cli_owned_turn(), accumulate_usage(), Merge one ``usage`` StreamEvent into the per-turn accumulation     ``state`` dic, _make_slim_history() (+17 more)

### Community 35 - "Community 35"
Cohesion: 0.11
Nodes (25): _atomic_write_text(), LLMConfig, LLMConfigError, load_llm_config(), Any, BaseModel, Exception, field_validator (+17 more)

### Community 36 - "Community 36"
Cohesion: 0.11
Nodes (17): Path, Render snapshot recording into the RenderSnapshotStore (Phase 4 T4)., Resolve the SQLite path for a project's render snapshots.      Mirrors the chat-, Append a snapshot to the RenderSnapshotStore.      ``success=True`` records a `r, record_snapshot(), _snapshots_path(), _Registry, BaseModel (+9 more)

### Community 37 - "Community 37"
Cohesion: 0.11
Nodes (23): applyTheme(), COMMANDS, fetchLLMConfig(), filteredCommands, formatPreviewDiagnostics(), initTheme(), llmModelSelect, llmProviderSelect (+15 more)

### Community 38 - "Community 38"
Cohesion: 0.17
Nodes (27): addAssetToTimeline(), addNoteAtPlayhead(), deleteEdit(), handleFiles(), hideEditDetail(), _isPlayableRender(), isProxyStale(), loadProjectState() (+19 more)

### Community 39 - "Community 39"
Cohesion: 0.17
Nodes (25): _cached_done_result(), _canonicalize_project_id(), execute_tool(), execute_trigger_render(), _is_error_result(), _normalise_preview_params(), _payload_hash(), preview_chunks_enabled() (+17 more)

### Community 40 - "Community 40"
Cohesion: 0.13
Nodes (24): _close_frame_clients(), _duplicate_away(), _frame_fd_is_open(), MeltTimeoutError, PipeResult, PipeRunError, Any, Exception (+16 more)

### Community 41 - "Community 41"
Cohesion: 0.13
Nodes (25): build_render_plan(), _default_emission_profile(), _enqueue_missing_source_proxy(), _frame_overlay_specs(), BaseModel, EmissionProfile, Render plan building: asset resolution, overlay planning, melt timeline., Resolve asset hashes → filesystem paths.      Collects hashes from applied ops, (+17 more)

### Community 42 - "Community 42"
Cohesion: 0.09
Nodes (12): CLIAdapter, _JCodeAdapter, _normalize_pi_object(), _pi_normalize_event(), Any, Protocol, Map one raw pi stdout line to 0..n StreamEvents.          JSON-lines input: deco, Map one parsed pi JSON event to one or more of our StreamEvent dicts.      Pi's (+4 more)

### Community 43 - "Community 43"
Cohesion: 0.12
Nodes (21): _Element, _emit_audio_micro_fade(), _emit_filter(), emit_timeline(), _emit_transition(), EmitterConfig, _format_timecode(), BaseModel (+13 more)

### Community 44 - "Community 44"
Cohesion: 0.14
Nodes (23): load_project(), Load a Project from the project directory.      For read-back operations. Raises, Project, _effects_for_clip(), _get_default_catalog(), _known_clip_ids(), _known_effect_ids(), _known_ids_from_ops() (+15 more)

### Community 45 - "Community 45"
Cohesion: 0.09
Nodes (20): generate_remotion_composition(), Any, Path, Agent tool: append AddRemotionCompositionOp (and optionally scaffold)., init_remotion_project(), Any, Path, Agent tool: scaffold a Remotion project under ``.open_edit/remotion/``. (+12 more)

### Community 46 - "Community 46"
Cohesion: 0.11
Nodes (23): BackgroundTasks, get_thumbnail(), post_create_project(), post_ingest(), Any, JSONResponse, Path, post (+15 more)

### Community 47 - "Community 47"
Cohesion: 0.15
Nodes (23): HTTPException, _check_rate_limit(), cancel_render_job(), get_render_file(), get_render_job(), get_renders(), _path_under_project(), post_render() (+15 more)

### Community 48 - "Community 48"
Cohesion: 0.13
Nodes (17): _mode_default_quality(), preview_chunk_profile(), preview_profile_fingerprint(), profile_fingerprint(), profile_with_quality(), BaseModel, field_validator, PreviewPlane (+9 more)

### Community 49 - "Community 49"
Cohesion: 0.13
Nodes (21): _extract_token(), _is_localhost(), _is_localhost_websocket(), BaseHTTPMiddleware, Request, Response, WebSocket, Authentication, WebSocket auth, and rate limiting for the Open Edit server.  Ext (+13 more)

### Community 50 - "Community 50"
Cohesion: 0.13
Nodes (23): _accumulate_session_usage(), compute_anthropic_cost(), compute_openai_cost(), default_pi_sessions_dir(), encoded_cwd_segment(), find_pi_session_file(), _iter_files(), load_pricing() (+15 more)

### Community 51 - "Community 51"
Cohesion: 0.13
Nodes (23): _chromium_available(), collect_diagnostics(), _config_summary(), _disk_free_bytes(), get_health(), _mlt_available(), System health & diagnostics collection for the open_edit server.  Provides three, Return actionable, redacted details about the selected sandbox. (+15 more)

### Community 52 - "Community 52"
Cohesion: 0.18
Nodes (23): _active_preview_job(), _artifact_mime(), _cache_for_project(), delete_preview_chunks(), get_preview_chunk_file(), get_preview_chunks(), _manifest_payload(), _path_under_project() (+15 more)

### Community 53 - "Community 53"
Cohesion: 0.10
Nodes (19): get_asset_or_error(), Exception, Canonical tool result contract.  Every agent tool wrapper returns one of three s, Base class for tool-domain errors surfaced as ``{"status": "error"}``., Tool error that should be retried later (e.g. transcription pending).      Norma, Look up an asset in the project's CAS.      Returns ``(asset, None)`` on success, Check an asset has word-level alignment.      Returns ``None`` when ``asset.alig, require_alignment() (+11 more)

### Community 54 - "Community 54"
Cohesion: 0.18
Nodes (22): Decorator: catch exceptions and return the canonical error dict.      ``ToolRetr, tool_result(), make_ir(), Create an IR instance backed by the project's EditGraphStore.      For mutating, add_clip(), add_hyperframes_overlay(), apply_silence_gaps(), change_clip_speed() (+14 more)

### Community 55 - "Community 55"
Cohesion: 0.15
Nodes (22): _bounded_error(), _contractualize_diagnostics(), _env_truthy(), _fail(), _frame_pull_fallback_requested(), frame_pull_gate(), _gpu_decode_available(), BaseModel (+14 more)

### Community 56 - "Community 56"
Cohesion: 0.17
Nodes (22): _append_interval(), _as_mapping(), _composition_changed(), DirtySelection, _entry_identity(), _entry_interval(), _index_entries(), _intersects_any() (+14 more)

### Community 57 - "Community 57"
Cohesion: 0.11
Nodes (9): _AnthropicAdapter, _AntigravityAdapter, _BaseCLIAdapter, _OpenAIAdapter, Default: decode each stdout line and map it via ``normalize_event``.          Li, SDK adapter stub for model discovery. No CLI binary involved., SDK adapter stub for model discovery. No CLI binary involved., Plain-text output: every stdout line is one ``text_delta``.          The line (i (+1 more)

### Community 58 - "Community 58"
Cohesion: 0.10
Nodes (20): 1.1 Core Flow & Primary Functions, 1. MLT XML Emission Architecture in `emitter.py`, 2.1 Filter Emission (`_emit_filter`), 2.2 OpenEdit IR Catalog Spec for `volume`, 2. Filter Representation & Attachment in `open_edit`, 3.1 Objective & Rationale, 3.2 Frame Count & Keyframe Calculation, 3.3 Target XML Output Example (+12 more)

### Community 59 - "Community 59"
Cohesion: 0.10
Nodes (20): 1.1 Document Hierarchy & Entry Generation, 1.2 How Filters are Attached to Playlist Clip Entries, 1. Audio Properties & Filter Attachment Mechanism in `emitter.py`, 2.1 Standardized Filter Service in `open_edit`, 2.2 XML Keyframe Representation for Micro-Fades, 2.3 Cascading Multiplier Behavior with User Filters, 2. MLT Filter Names & Properties for Audio Volume Fades, 3.1 Timecode & Frame Calculation Rules in `emitter.py` (+12 more)

### Community 60 - "Community 60"
Cohesion: 0.16
Nodes (20): EncoderBackend, apply_overrides(), apply_profile_vcodec(), detect_gpu_vcodec(), _ffmpeg(), ffmpeg_video_args(), _override_pairs(), _probe_encoder() (+12 more)

### Community 61 - "Community 61"
Cohesion: 0.10
Nodes (19): 1. Executive Summary, 2.1 Inventory of `open_edit/serve/visual_verify.py`, 2.2 Usage in `open_edit/serve/agent.py`, 2. Codebase Baseline & Function Inventory, 3.1 Concept & Layout Strategy, 3.2 Composite Layout Modes, 3. Architecture Design: Dual-Panel Waveform Composite Image Generation, 4.1 Standard Case: Video + Audio (`has_video=True`, `has_audio=True`) (+11 more)

### Community 62 - "Community 62"
Cohesion: 0.15
Nodes (17): boundedError(), bundleCache, compositionCache, config, getBundle(), getComposition(), input, isInside() (+9 more)

### Community 63 - "Community 63"
Cohesion: 0.13
Nodes (19): build_qc_evidence(), build_verification_tool_result(), encode_jpeg(), _is_summary(), model_capability(), parse_verdict(), prune_images(), Any (+11 more)

### Community 64 - "Community 64"
Cohesion: 0.24
Nodes (18): composition_cache_key(), composition_source_bundle(), _iter_prop_strings(), Any, Path, Remotion safety and source-hashing helpers.  Entry-point validation, composition, Copy local composition assets into Remotion's safe public directory.      Remoti, Hash referenced files, following symlinks to their target bytes. (+10 more)

### Community 65 - "Community 65"
Cohesion: 0.16
Nodes (16): generate_visual(), MotionTemplateParams, BaseModel, Path, Motion graphics engine: runs templates to produce video assets.  Per phase4-desi, Parameters consumed by every motion-graphics template.      ``asset_references``, Run a motion-graphics template, ingest the output, emit AddClipOp.      Args:, analyze() (+8 more)

### Community 66 - "Community 66"
Cohesion: 0.11
Nodes (17): 1. Executive Summary, 2. Codebase Baseline Observation, 3.1 Corner Case 1: Audio-Only Inputs (MP3, WAV, AAC, or MP4 without video stream), 3.2 Corner Case 2: Video-Only Inputs (Silent video clips without audio track), 3.3 Corner Case 3: Short Clip Windows & Boundary Timestamps, 3.4 Corner Case 4: Missing FFmpeg Binary, 3.5 Corner Case 5: Error Handling & Subprocess Failures, 3. Comprehensive Corner Case Analysis (+9 more)

### Community 67 - "Community 67"
Cohesion: 0.22
Nodes (16): Shared editing kernel — tool dispatch, render jobs, pillar schemas.  Used by the, _append_ir_op(), _apply_generated_ops(), dispatch_edit(), dispatch_generate(), dispatch_query(), Any, Path (+8 more)

### Community 68 - "Community 68"
Cohesion: 0.15
Nodes (15): OverlayInput, build_pipe_commands(), _fps_string(), overlay_filter_chain(), PipeCommands, Path, Frame-server pipe: melt -> rawvideo stdout -> ffmpeg single encode.  melt compos, Build melt-video, melt-audio, and ffmpeg commands for one render. (+7 more)

### Community 69 - "Community 69"
Cohesion: 0.11
Nodes (15): absEntry, absOut, absRoot, compositionId, concurrency, extraArgs, imageFormat, output (+7 more)

### Community 70 - "Community 70"
Cohesion: 0.22
Nodes (17): _cost_sidecar_path(), _create_bg_task(), emit_cost_update(), _load_cost_state(), Any, Path, Cost sidecar persistence (v1.4 P1-3).  The cumulative session cost is persisted, Async save — runs the disk I/O on a thread so the WS loop     stays responsive. (+9 more)

### Community 71 - "Community 71"
Cohesion: 0.18
Nodes (14): Internal: a single op in ops.jsonl failed referential or schema validation., _ValidationError, _assets_dir_for_workdir(), _FlushingBuffer, _load_assets_via_store(), _load_project_for_validation(), Path, Shared staging / collect / cleanup for free-form sandbox runs.  Both backends st (+6 more)

### Community 72 - "Community 72"
Cohesion: 0.15
Nodes (16): _looks_like_bwrap_unavailable(), CompletedProcess, Exception, Path, Free-form sandbox execution backends.  ``get_sandbox_backend()`` selects the bac, 5b: make a string safe to surface in a result detail.      - Take only the first, Return True if the process output indicates bwrap could not create     the names, Fail-closed signal: the bwrap sandbox could not be created.      Raised ONLY whe (+8 more)

### Community 73 - "Community 73"
Cohesion: 0.12
Nodes (15): find_silence_gaps(), no_word_split_check(), propose_cuts(), Silence cutter skill: propose cuts at silence gaps.  Per phase4-design-revised.m, Check if a cut at [t_start, t_end] splits any word.      A cut splits a word if, Find silence intervals >= ``threshold_ms`` in source time.      Returns a list o, Return gap-based cut suggestions for `asset`.      Each suggestion is a dict::, get_transcript_packed() (+7 more)

### Community 74 - "Community 74"
Cohesion: 0.12
Nodes (16): 1. Observation, 2. Logic Chain, 3. Caveats, 4. Conclusion, 5. Verification Method, Actionable Fix Suggestions for Worker 1:, [Critical] Finding 1: INTEGRITY VIOLATION — Facade Test Assertion Self-Certifying Muted Short Clips, Findings (+8 more)

### Community 75 - "Community 75"
Cohesion: 0.14
Nodes (13): BinaryIO, _bounded_error(), frame_pull_platform_supported(), FrameFeederError, probe_frame_pull_host(), Path, RuntimeError, Incremental Remotion PNG feeding for the experimental ffmpeg pipe path.  The fee (+5 more)

### Community 76 - "Community 76"
Cohesion: 0.14
Nodes (11): compute_edit_graph_hash(), Canonical hashing of an edit graph for timeline snapshot caching., Return a stable sha256 hex digest for a list of operations.      Accepts op obje, derive_or_load_timeline(), Path, Timeline snapshot cache policy over an ``EditGraphStore``.  ``derive_or_load_tim, SQLite store for derived timeline snapshots keyed by edit-graph hash., Store a derived timeline snapshot keyed by edit-graph hash. (+3 more)

### Community 77 - "Community 77"
Cohesion: 0.23
Nodes (16): PreviewMedia, _build_audio_command(), _build_mux_command(), build_preview_pipe_commands(), _build_video_command(), _fps_string(), _mux_temp_path(), _pipeline() (+8 more)

### Community 78 - "Community 78"
Cohesion: 0.21
Nodes (16): AudioLevels, _ffmpeg(), get_audio_levels(), _has_audio_stream(), _last_stderr_line(), list_silence(), _parse_db(), _parse_overall_db() (+8 more)

### Community 79 - "Community 79"
Cohesion: 0.18
Nodes (14): compact_history(), ContextBudget, count_tokens(), count_tokens_history(), count_tokens_message(), _has_tool_result(), Any, Token counting and sliding-window history truncation for context budget manageme (+6 more)

### Community 80 - "Community 80"
Cohesion: 0.17
Nodes (15): candidate_dirs(), discover_runtimes(), find_binary_in_expanded_path(), get_expanded_path_env(), Any, Path, v1.8 — Runtime Registry & GUI PATH Expansion.  All provider metadata is defined, Specification and status of an LLM runtime.      Fields are derived from the can (+7 more)

### Community 81 - "Community 81"
Cohesion: 0.20
Nodes (11): FreeFormResult, Result of a free-form Python run. Always returned, never raised.      success=Tr, BwrapBackend, Default, secure backend: the Rust ``open-edit-sandbox`` binary     (bwrap + secc, Bootstrap codegen: render ``_bootstrap.py`` for in-sandbox execution.  C2 prefer, Generate _bootstrap.py with the IR class and op models inlined.      C2 preferre, render_bootstrap(), _free_form_failure() (+3 more)

### Community 82 - "Community 82"
Cohesion: 0.20
Nodes (15): _coerce_positive_int(), Path, Free-form / render facades: orchestration, error mapping, never-raises.  Kept th, P9: resolve a caller-supplied workdir.      The AI may operate on any directory;, Run free-form Python in the sandbox. NEVER raises (C7).      `originating_note_i, Run a render and always return a structured result., Run heavy-compute code in the render sandbox. Returns a RenderResult     (never, Return a bounded, single-line detail safe to show to an agent.      Backend deta (+7 more)

### Community 83 - "Community 83"
Cohesion: 0.17
Nodes (14): build_prior_state(), _format_slice(), _load_profile(), Builds the prior_state block for the system prompt.  Per phase4-design-revised.m, _db_path(), get_asset_store(), _notes_db_path(), _project_root() (+6 more)

### Community 84 - "Community 84"
Cohesion: 0.12
Nodes (15): 1. Corner Cases for 30ms Audio Micro-Fades, 2. Pytest Environment, Test Structure & Helper Dependencies, 3. Edge Cases & Potential Regression Risks in `emitter.py`, 4. Exact Implementation Recommendations, 5. Recommended Unit Tests (`tests/test_render/test_emitter.py`), A. Clips Shorter than 60ms (< 60ms, down to 1 frame / 0s), A. EmitterConfig Extension (`open_edit/render/emitter.py`), A. Test Execution & Location (+7 more)

### Community 85 - "Community 85"
Cohesion: 0.12
Nodes (15): 1. Architectural Overview & Context, 2.1 Storage & IR Layer (`open_edit/storage/transcription.py` & `open_edit/ir/types.py`), 2.2 Agent Tools Layer (`open_edit/agent/tools/`), 2.3 Pillar Tools & Schema Registration (`open_edit/serve/`), 2. Codebase Investigation Findings, 3.1 Data Flow & Algorithm Steps, 3.2 Detailed Formatting Rules, 3. Phrase Packing Algorithm Specification (+7 more)

### Community 86 - "Community 86"
Cohesion: 0.19
Nodes (15): derive_tags_and_triggers(), extract_file_metadata(), generate_manifest(), index_assets(), main(), parse_fps(), Any, Asset Indexer Module for OpenEdit / mlt-pipeline.  Scans the assets directory, e (+7 more)

### Community 87 - "Community 87"
Cohesion: 0.21
Nodes (13): CancelRenderJobArgs, EditProjectArgs, GetRenderJobArgs, BaseModel, QueryProjectArgs, Pydantic-backed registry of Open Edit tool argument schemas.  Single source of t, RunScriptArgs, TriggerRenderArgs (+5 more)

### Community 88 - "Community 88"
Cohesion: 0.17
Nodes (10): MeltRunner, CompletedProcess, Path, Build and run melt commands, mediating the render cache.      Cache lookup happe, Look up a cached render for ``key`` (None if absent)., True if the cached file is younger than the cache freshness window., Copy ``source_path`` into the cache under ``key``. Returns the cached path., Build the melt command line. (+2 more)

### Community 89 - "Community 89"
Cohesion: 0.17
Nodes (12): new_conversation_id(), The Open Edit agent loop.  ``run_agent_turn`` is an async generator that:  1. Bu, _build_state_summary(), _build_system_prompt(), System prompt construction (DETERMINISTIC — see hard requirement #5)., Return a brief summary of the project state (under 1KB)., Build the system prompt.      Deterministic: the same ``state`` always produces, open_edit.serve — FastAPI chat-driven backend for the Open Edit video editor.  T (+4 more)

### Community 90 - "Community 90"
Cohesion: 0.23
Nodes (15): autoGrowInput(), bindEvents(), executeCmd(), filterCmdList(), handleCmdKeydown(), handleSend(), openCmdPalette(), openNotesModal() (+7 more)

### Community 91 - "Community 91"
Cohesion: 0.17
Nodes (9): ProjectPaths, Path, Single source of truth for the on-disk project layout.  Canonical server layout, Resolved paths for one Open Edit project directory.      ``root`` is the project, Resolve from a sandbox workdir.          A workdir is the directory that directl, The project's ``edit_graph.db``.          Canonical ``<root>/.open_edit/edit_gra, Notes live at the project ROOT (``<root>/notes.db``), NOT inside         ``.open, The project's asset CAS root: ``<root>/.open_edit/assets``. (+1 more)

### Community 92 - "Community 92"
Cohesion: 0.17
Nodes (9): AssetResolver, get_resolver(), Any, Asset Resolver Module for OpenEdit / mlt-pipeline.  Provides semantic asset retr, Interface for querying and resolving media assets from open_edit/assets_manifest, Loads assets from the JSON manifest file., Finds the best matching asset for a given AI trigger event., Filters assets by category, subcategory, tags, or media_type. (+1 more)

### Community 93 - "Community 93"
Cohesion: 0.13
Nodes (14): Color, audio, overlays — the free-form escape hatch, Cut dead air on sense boundaries, not raw gaps, Edit planning, Input, Match the target duration, Output, Pacing, Rules (+6 more)

### Community 94 - "Community 94"
Cohesion: 0.16
Nodes (15): _asset_proxy_job_response(), AssetProxyJobResponse, AssetProxyRequest, get_asset_file(), get_asset_proxy_job(), _guess_mime_type(), post_asset_proxy(), BaseModel (+7 more)

### Community 95 - "Community 95"
Cohesion: 0.19
Nodes (12): MusicTrack, BaseModel, Music selector skill: pick mood-matched tracks for narrative segments.  Per phas, Pick tracks using mood first and duration fit as a tie-breaker., Return a modest energy prior used only to break equal-fit ties., select(), _target_energy(), _load_music_library() (+4 more)

### Community 96 - "Community 96"
Cohesion: 0.14
Nodes (13): 1. Executive Summary, 2.1 Storage & Transcription Models, 2. Existing Data Structures & Architecture Analysis, 3.1 Phrase Packing Algorithm, 3.2 Timestamp Formatting, 3.3 Output Markdown Format, 3.4 Edge Case Handling, 3. Data Format Specification for `takes_packed.md` (+5 more)

### Community 97 - "Community 97"
Cohesion: 0.14
Nodes (13): 1. Observation, 2. Logic Chain, 3. Caveats, 4. Conclusion, 5. Verification Method, Coverage Gaps, Handoff Report — Milestone 3 (R3: Waveform Cut Inspection Image Generation), Implementation Inspection (`open_edit/serve/visual_verify.py`) (+5 more)

### Community 98 - "Community 98"
Cohesion: 0.16
Nodes (14): exception_handler, diagnostics(), get_health(), health(), _http_exception_handler(), Any, Exception, get (+6 more)

### Community 99 - "Community 99"
Cohesion: 0.24
Nodes (13): append_to_conversation(), _build_tool_result_message(), _compact_jsonl(), _conversations_dir(), load_conversation(), Any, Path, Conversation persistence for the agent loop.  The conversation history is persis (+5 more)

### Community 100 - "Community 100"
Cohesion: 0.21
Nodes (12): current_version(), ensure_schema(), _migration_files(), Connection, Path, Lightweight, safe SQLite migration runner for the edit-graph store.  Schema evol, Return the schema version recorded in ``PRAGMA user_version``., Map migration id -> SQL file path, discovered from this directory. (+4 more)

### Community 101 - "Community 101"
Cohesion: 0.21
Nodes (11): place(), BaseModel, SFX placer skill: place sound effects at narrative beat transitions.  Per phase4, Place duration-fit SFX at transitions, aligned to music when possible., SfxClip, _load_sfx_library(), place_sfx(), pyagent_place_sfx: returns SFX placement ops at beat transitions.  Per phase4-de (+3 more)

### Community 102 - "Community 102"
Cohesion: 0.21
Nodes (7): EffectCatalog, EffectSpec, ParamSpec, BaseModel, Path, Load the effect catalog from a directory of YAML files., In-memory registry of effect specs loaded from YAML.

### Community 103 - "Community 103"
Cohesion: 0.21
Nodes (12): delete_op(), _invalidate_project_snapshots(), move_arbitrary(), Connection, Edit-graph ordering operations.  The reorder/delete family rewrites ``edits.sequ, Atomically replace the complete edit ordering.      Callers must supply every ed, Swap the sequence_num of two adjacent operations.      Raises ValueError if eith, Delete cached timeline snapshot rows for the project (one db per project). (+4 more)

### Community 104 - "Community 104"
Cohesion: 0.17
Nodes (11): Active Timers, Artifact Index, BRIEFING — 2026-07-23T13:32:22+03:00, Current Parent, 🔒 Key Constraints, Key Decisions Made, Mission, 🔒 My Identity (+3 more)

### Community 105 - "Community 105"
Cohesion: 0.17
Nodes (11): 1. Observation, 2. Logic Chain, 3. Caveats, 4. Conclusion, 5. Verification Method, Adversarial Edge Case Verification Results, Code Files Inspected, Handoff Report: Reviewer 2 (Milestone 2 - R2: Token-Efficient Phrase-Packed Transcript Tool) (+3 more)

### Community 106 - "Community 106"
Cohesion: 0.17
Nodes (11): Artifact Index, BRIEFING — 2026-07-23T13:36:25Z, Change Tracker, Current Parent, 🔒 Key Constraints, Key Decisions Made, Loaded Skills, Mission (+3 more)

### Community 107 - "Community 107"
Cohesion: 0.17
Nodes (11): Artifact Index, BRIEFING — 2026-07-23T13:44:00Z, Change Tracker, Current Parent, 🔒 Key Constraints, Key Decisions Made, Loaded Skills, Mission (+3 more)

### Community 108 - "Community 108"
Cohesion: 0.17
Nodes (11): Artifact Index, BRIEFING — 2026-07-23T13:39:00Z, Change Tracker, Current Parent, 🔒 Key Constraints, Key Decisions Made, Loaded Skills, Mission (+3 more)

### Community 109 - "Community 109"
Cohesion: 0.17
Nodes (11): Artifact Index, BRIEFING — 2026-07-23T13:41:00Z, Change Tracker, Current Parent, 🔒 Key Constraints, Key Decisions Made, Loaded Skills, Mission (+3 more)

### Community 110 - "Community 110"
Cohesion: 0.17
Nodes (11): Artifact Index, BRIEFING — 2026-07-23T13:49:00+03:00, Change Tracker, Current Parent, 🔒 Key Constraints, Key Decisions Made, Loaded Skills, Mission (+3 more)

### Community 111 - "Community 111"
Cohesion: 0.26
Nodes (11): _check_type(), Any, ValueError, Hand-rolled schema validation for Open Edit tool arguments.  Validates tool argu, Return an error dict if validation fails, or None if valid., Raised when tool arguments don't match the schema., Check that ``value`` matches ``expected_type``.      ``number`` accepts both ``i, Validate ``args`` against the schema for ``name``.      Raises ``SchemaValidatio (+3 more)

### Community 112 - "Community 112"
Cohesion: 0.20
Nodes (11): build_tool_schemas(), Return Anthropic-shaped tool schemas generated from the registry., dispatch_mcp_tool(), mcp_tool_schemas(), Any, Path, Map MCP tool calls onto Open Edit pillar dispatch.  ``project_path`` is injected, Anthropic-shaped schemas for pillars + render helpers. (+3 more)

### Community 113 - "Community 113"
Cohesion: 0.21
Nodes (10): detect_silence_spans(), FFprobeError, _last_stderr_line(), probe_duration(), Path, ValueError, Shared ffprobe/ffmpeg helpers used by render and qc.  Single home for silencedet, Raised when an ffmpeg/ffprobe probe exits non-zero (decode failure).      The me (+2 more)

### Community 114 - "Community 114"
Cohesion: 0.29
Nodes (11): build_keep_ranges(), compress_silence(), compress_silence_audio(), _concat_ranges(), extract_audio(), Path, Fast silence compression via ffconcat inpoint/outpoint stream copy.  Avoids the, Compress silences in an audio file; output is audio-only. (+3 more)

### Community 115 - "Community 115"
Cohesion: 0.32
Nodes (10): _elapsed(), _failure(), generate_asset_proxy(), Path, Per-asset low-resolution source-proxy generation., Generate or reuse one low-resolution source-proxy CAS object., _record_failure(), SourceProxyProfile (+2 more)

### Community 116 - "Community 116"
Cohesion: 0.21
Nodes (11): _build_verification_result(), _maybe_verify_render(), Any, Path, Visual verification helpers (v1.5)., Map a render error string to a ``verdict_source`` value., Build a single ``verification_result`` AgentEvent., Run the verification stage for one ``trigger_render`` result.      Returns ``(ev (+3 more)

### Community 117 - "Community 117"
Cohesion: 0.32
Nodes (11): _chmod(), _default_profile(), get_config_dir(), get_profile_path(), get_user_project_meta(), Path, Manages ~/.open-edit/ directory and config files., Return user-level (file-based) per-project metadata. Creates the file on first a (+3 more)

### Community 118 - "Community 118"
Cohesion: 0.21
Nodes (11): format_timestamp(), _has_whisper(), Path, faster-whisper integration for word-level alignment.  Per phase4-design-revised., Resolve Whisper model size from arg or ``OPEN_EDIT_WHISPER_MODEL``., Resolve language override from arg or ``OPEN_EDIT_WHISPER_LANGUAGE``.      Empty, Transcribe an audio/video file to word-level alignment.      ``model_size`` defa, Format seconds into timestamp string MM:SS.ms (or HH:MM:SS.ms if >= 1hr). (+3 more)

### Community 119 - "Community 119"
Cohesion: 0.18
Nodes (10): 1. Observation, 2. Logic Chain, 3. Caveats, 4. Conclusion, 5. Verification Method, Forensic Audit Report — Milestone 4 (Forensic Audit Gate), Overall Repository Test Suite Run, R1: Automatic 30ms Audio Micro-Fades (+2 more)

### Community 120 - "Community 120"
Cohesion: 0.18
Nodes (10): Artifact Index, Attack Surface, BRIEFING — 2026-07-23T13:49:06Z, Current Parent, 🔒 Key Constraints, Key Decisions Made, Mission, 🔒 My Identity (+2 more)

### Community 121 - "Community 121"
Cohesion: 0.18
Nodes (10): Artifact Index, Attack Surface, BRIEFING — 2026-07-23T13:47:23Z, Current Parent, 🔒 Key Constraints, Key Decisions Made, Mission, 🔒 My Identity (+2 more)

### Community 122 - "Community 122"
Cohesion: 0.18
Nodes (10): 1. Execute Unit Tests, 1. Observation, 2. File Inspection, 2. Logic Chain, 3. Caveats, 3. Invalidation Conditions, 4. Conclusion, 5. Verification Method (+2 more)

### Community 123 - "Community 123"
Cohesion: 0.18
Nodes (10): 1. Code Inspection Verification, 1. Observation, 2. Logic Chain, 2. Pytest Execution, 3. Caveats, 3. Invalidation Conditions, 4. Conclusion, 5. Verification Method (+2 more)

### Community 124 - "Community 124"
Cohesion: 0.18
Nodes (10): Artifact Index, Attack Surface, BRIEFING — 2026-07-23T10:37:46Z, Current Parent, 🔒 Key Constraints, Key Decisions Made, Mission, 🔒 My Identity (+2 more)

### Community 125 - "Community 125"
Cohesion: 0.18
Nodes (10): Artifact Index, Attack Surface, BRIEFING — 2026-07-23T13:37:30Z, Current Parent, 🔒 Key Constraints, Key Decisions Made, Mission, 🔒 My Identity (+2 more)

### Community 126 - "Community 126"
Cohesion: 0.18
Nodes (10): Artifact Index, Attack Surface, BRIEFING — 2026-07-23T13:40:40+03:00, Current Parent, 🔒 Key Constraints, Key Decisions Made, Mission, 🔒 My Identity (+2 more)

### Community 127 - "Community 127"
Cohesion: 0.18
Nodes (10): Artifact Index, Attack Surface, BRIEFING — 2026-07-23T13:40:05Z, Current Parent, 🔒 Key Constraints, Key Decisions Made, Mission, 🔒 My Identity (+2 more)

### Community 128 - "Community 128"
Cohesion: 0.18
Nodes (10): Artifact Index, Attack Surface, BRIEFING — 2026-07-23T10:45:00Z, Current Parent, 🔒 Key Constraints, Key Decisions Made, Mission, 🔒 My Identity (+2 more)

### Community 129 - "Community 129"
Cohesion: 0.18
Nodes (10): 1. Directory Tree & Taxonomy, 2. Naming Standards (English Only), 3. Natural Language AI Trigger Rules, 4.1 Audio Track Structure, 4.2 Visual Compositing & Blend Modes, 4. Track Layering & Audio Loudness Standards, 5. Technical Specifications & Compliance, 6. How AI Agents Query Assets Programmatically (+2 more)

### Community 130 - "Community 130"
Cohesion: 0.18
Nodes (10): Asset-reference failures at append, Cache policy and operator budgets, Over-aggressive cut density, QC policy, completeness, and budgets, QC standards, Re-running after a failure, Real-world failure modes (watch for these), Render products and emission policy (+2 more)

### Community 131 - "Community 131"
Cohesion: 0.31
Nodes (11): bindTimelineScrubbing(), copyPlayheadTimecode(), fitTimelineToWindow(), formatTimecode(), opPositionSec(), renderRuler(), renderTimeline(), secToPx() (+3 more)

### Community 132 - "Community 132"
Cohesion: 0.29
Nodes (8): get_style_profile(), pyagent_get_style_profile: returns the tag-gated style profile slice.  Per phase, Return the style profile slice for ``args['op_type']``.      Args:         args:, get_slice(), _load_profile(), Any, Tag-gated style profile retrieval for system prompt injection.  Per phase4-desig, _trim_to_token_cap()

### Community 133 - "Community 133"
Cohesion: 0.20
Nodes (9): Artifact Index, Audit Progress, Audit Scope, BRIEFING — 2026-07-23T10:52:47Z, Current Parent, 🔒 Key Constraints, Key Decisions Made, Mission (+1 more)

### Community 134 - "Community 134"
Cohesion: 0.20
Nodes (9): 2026-07-23T13:32:22+03:00, 2026-07-23T13:45:41+03:00, Acceptance Criteria, Automated Tests & Quality, Original User Request, R1. Automatic 30ms Audio Micro-Fades in MLT Emitter, R2. Token-Efficient Phrase-Packed Transcript Tool (`get_transcript_packed`), R3. Waveform Cut Inspection Image Generation (+1 more)

### Community 135 - "Community 135"
Cohesion: 0.20
Nodes (9): 1. Observation, 2. Logic Chain, 3. Caveats, 4. Conclusion, 5. Verification Method, Handoff Report — Milestone 4 (Full Test Suite Regression Verification), New Feature Unit Tests (Milestone 4 Targets), Test Execution Summary (+1 more)

### Community 136 - "Community 136"
Cohesion: 0.20
Nodes (9): 1. Observation, 2. Logic Chain, 3. Caveats, 4. Conclusion, 5.1 Files to Inspect, 5.2 Verification Commands, 5.3 Invalidation Conditions, 5. Verification Method (+1 more)

### Community 137 - "Community 137"
Cohesion: 0.20
Nodes (9): Artifact Index, Audit Progress, Audit Scope, BRIEFING — 2026-07-23T13:56:20Z, Current Parent, 🔒 Key Constraints, Key Decisions Made, Mission (+1 more)

### Community 138 - "Community 138"
Cohesion: 0.22
Nodes (6): How hosts should load them, Not agent skills, Open Edit harness skills, Planning & QC, Start here, Legacy Remotion migration

### Community 139 - "Community 139"
Cohesion: 0.20
Nodes (10): 1. `query_project` (read-only), 2. `edit_project` (mutations + creative generation), 3. `run_script` (free-form Python), 4. `trigger_render`, Authoritative source, Common mistakes (do not repeat these), `preview-chunks` job contract, Priority order (always follow this) (+2 more)

### Community 140 - "Community 140"
Cohesion: 0.29
Nodes (9): apply_command(), EditGraphCommandError, open_store(), Any, Path, ValueError, Shared edit-graph mutation service for AI tools and the manual UI.  All interact, User-facing command validation failure. (+1 more)

### Community 141 - "Community 141"
Cohesion: 0.20
Nodes (4): OPEN_EDIT_PKG, REAL_DIR, REAL_FILE, ToolDef

### Community 142 - "Community 142"
Cohesion: 0.33
Nodes (9): clearAssetsList(), setAssetsLoading(), assetIcon(), openAssetPreview(), renderAssets(), appendSearchResults(), _renderSearchResultCard(), el() (+1 more)

### Community 143 - "Community 143"
Cohesion: 0.22
Nodes (8): 2026-07-23T10:32:04Z, Acceptance Criteria, Automated Tests & Quality, Original User Request, R1. Automatic 30ms Audio Micro-Fades in MLT Emitter, R2. Token-Efficient Phrase-Packed Transcript Tool (`get_transcript_packed`), R3. Waveform Cut Inspection Image Generation, Requirements

### Community 144 - "Community 144"
Cohesion: 0.22
Nodes (8): Artifact Index, BRIEFING — 2026-07-23T13:32:15+03:00, 🔒 Key Constraints, Mission, 🔒 My Identity, Project Status, User Context, Victory Audit Status

### Community 145 - "Community 145"
Cohesion: 0.22
Nodes (8): Artifact Index, BRIEFING — 2026-07-23T10:34:25Z, Current Parent, Investigation State, 🔒 Key Constraints, Key Decisions Made, Mission, 🔒 My Identity

### Community 146 - "Community 146"
Cohesion: 0.22
Nodes (8): Artifact Index, BRIEFING — 2026-07-23T10:35:10Z, Current Parent, Investigation State, 🔒 Key Constraints, Key Decisions Made, Mission, 🔒 My Identity

### Community 147 - "Community 147"
Cohesion: 0.22
Nodes (8): Artifact Index, BRIEFING — 2026-07-23T10:32:44Z, Current Parent, Investigation State, 🔒 Key Constraints, Key Decisions Made, Mission, 🔒 My Identity

### Community 148 - "Community 148"
Cohesion: 0.22
Nodes (8): Artifact Index, BRIEFING — 2026-07-23T10:36:15Z, Current Parent, Investigation State, 🔒 Key Constraints, Key Decisions Made, Mission, 🔒 My Identity

### Community 149 - "Community 149"
Cohesion: 0.22
Nodes (8): Artifact Index, BRIEFING — 2026-07-23T10:37:00Z, Current Parent, Investigation State, 🔒 Key Constraints, Key Decisions Made, Mission, 🔒 My Identity

### Community 150 - "Community 150"
Cohesion: 0.22
Nodes (8): Artifact Index, BRIEFING — 2026-07-23T10:38:50Z, Current Parent, Investigation State, 🔒 Key Constraints, Key Decisions Made, Mission, 🔒 My Identity

### Community 151 - "Community 151"
Cohesion: 0.22
Nodes (8): Artifact Index, BRIEFING — 2026-07-23T10:37:40Z, Current Parent, Investigation State, 🔒 Key Constraints, Key Decisions Made, Mission, 🔒 My Identity

### Community 152 - "Community 152"
Cohesion: 0.22
Nodes (9): Common edits, Common reads, Motion graphics, Open Edit MCP — agent playbook, Priority, Render products, Render workflow, Token rule (+1 more)

### Community 153 - "Community 153"
Cohesion: 0.22
Nodes (8): Architecture, Code Layout, Emitter ↔ MLT Engine, Interface Contracts, Milestones, Project: Open Edit Features Implementation, Transcription ↔ Agent Tools, Visual Verify ↔ FFmpeg

### Community 154 - "Community 154"
Cohesion: 0.33
Nodes (8): BlackFramesResult, BlackSpan, list_black_frames(), _parse_blackdetect(), BaseModel, Black-frame detection for QC.  Wraps ffmpeg's blackdetect filter. A frame is "bl, Parse blackdetect lines from ffmpeg's stderr., Return black-frame spans for the [in_sec, out_sec] range.      ``scale_height``

### Community 155 - "Community 155"
Cohesion: 0.33
Nodes (8): FrozenFramesResult, FrozenSpan, list_frozen_frames(), _parse_freezedetect(), BaseModel, Frozen-frame detection for QC.  Wraps ffmpeg's ``freezedetect`` filter. A segmen, Parse freezedetect lines from ffmpeg's stderr.      freezedetect emits a ``freez, Return frozen-frame spans for a source range.      The optional range is useful

### Community 156 - "Community 156"
Cohesion: 0.22
Nodes (8): description, main, name, private, scripts, check, type, version

### Community 157 - "Community 157"
Cohesion: 0.44
Nodes (8): capture_hint(), _load_profile(), Any, Style profile persistence (pinned overrides + confirmed hints).  Per phase4-desi, Persist a confirmed style hint with provenance.      Also pins ``key=value`` whe, set_pinned(), _touch_meta(), _write_profile_with_backup()

### Community 158 - "Community 158"
Cohesion: 0.29
Nodes (7): DevSubprocessBackend, get_sandbox_backend(), Pluggable execution backend for a free-form Python run.      A backend receives, Execute the run and return a FreeFormResult (may raise         SandboxUnavailabl, UNSAFE local-dev backend. Runs the generated bootstrap + user code in     a plai, Select the free-form sandbox backend from the environment.      Env contract (``, SandboxBackend

### Community 159 - "Community 159"
Cohesion: 0.25
Nodes (7): Execution Plan: Open Edit 3 Features Implementation, Milestone 1: R1. Automatic 30ms Audio Micro-Fades in MLT Emitter, Milestone 2: R2. Token-Efficient Phrase-Packed Transcript Tool (`get_transcript_packed`), Milestone 3: R3. Waveform Cut Inspection Image Generation, Milestone 4: Full Suite Regression Verification & Final Sign-off, Milestones, Overview

### Community 160 - "Community 160"
Cohesion: 0.25
Nodes (7): 1. Observation, 2. Logic Chain, 3. Caveats, 4. Conclusion, 5. Verification Method, Implementation Checklist for Implementer:, Milestone 2 (R2): Token-Efficient Phrase-Packed Transcript Tool Handoff Report

### Community 161 - "Community 161"
Cohesion: 0.25
Nodes (7): 1. Code Changes (`open_edit/render/emitter.py`), 2. Test Updates & Additions (`tests/test_render_emitter.py`), 3. Verification Test Run & Output, Command Run:, `_emit_audio_micro_fade` Keyframe Calculation & Deduplication Fix:, Result:, Summary of Fixes — Worker 1 Fix Agent (Milestone 1)

### Community 162 - "Community 162"
Cohesion: 0.25
Nodes (7): Free-form ops & effect catalog — reference, Free-form ops (escape hatch), Relevant source (read these in the real codebase), Structured effect catalog, Validation gap — read this before using free-form, What you CANNOT do, When to escape to free-form

### Community 163 - "Community 163"
Cohesion: 0.25
Nodes (7): Authoritative code (debug Open Edit only), Dual process (MCP + review UI), Env knobs (config, not code), Example tool arguments, IR op kinds (high level), Open Edit MCP reference, When to use `run_script`

### Community 164 - "Community 164"
Cohesion: 0.29
Nodes (6): Exception, Exception types and result types for the free-form Python sandbox., Result of a render-sandbox run (Phase 4.5 W2).      Distinct from open_edit.rend, Raised for unrecoverable preflight/setup errors. NOT for runtime failures     (t, RenderResult, SandboxError

### Community 165 - "Community 165"
Cohesion: 0.38
Nodes (6): lib_version_supported(), _load_manifest(), parse_header(), Parse `# ir_api_version: X.Y; libs: {...}` headers and check against the allowed, Parse the ir_api_version header from a free-form Python script.      Returns (ve, version_supported()

### Community 166 - "Community 166"
Cohesion: 0.29
Nodes (6): Active Subagents, Key Artifacts, Milestone State, Observation & Summary of Work Completed So Far, Remaining Work for Successor (Gen 2), Soft Handoff Report — Project Orchestrator (Gen 1 -> Gen 2)

### Community 167 - "Community 167"
Cohesion: 0.29
Nodes (6): 1. Observation, 2. Logic Chain, 3. Caveats, 4. Conclusion, 5. Verification Method, Milestone 4 Verification (Run 2) Handoff Report

### Community 168 - "Community 168"
Cohesion: 0.29
Nodes (6): 1. Observation, 2. Logic Chain, 3. Caveats, 4. Conclusion, 5. Verification Method, Handoff Report: Milestone 1 (Explorer 3 - Corner Cases & Test Implementation)

### Community 169 - "Community 169"
Cohesion: 0.29
Nodes (6): 1. Observation, 2. Logic Chain, 3. Caveats, 4. Conclusion, 5. Verification Method, Handoff Report: Milestone 3 (R3: Waveform Cut Inspection Image Generation)

### Community 170 - "Community 170"
Cohesion: 0.29
Nodes (6): 1. Observation, 2. Logic Chain, 3. Caveats, 4. Conclusion, 5. Verification Method, Handoff Report: Waveform Cut Inspection Edge Case Analysis & Unit Test Strategy (Milestone 3 / R3)

### Community 171 - "Community 171"
Cohesion: 0.29
Nodes (6): 1. Observation, 2. Logic Chain, 3. Caveats, 4. Conclusion, 5. Verification Method, Handoff Report — Reviewer 2 (Milestone 1: 30ms Audio Micro-Fades in MLT Emitter)

### Community 172 - "Community 172"
Cohesion: 0.29
Nodes (6): 1. Observation, 2. Logic Chain, 3. Caveats, 4. Conclusion, 5. Verification Method, Handoff Report — Milestone 2 Review (Token-Efficient Phrase-Packed Transcript Tool)

### Community 173 - "Community 173"
Cohesion: 0.29
Nodes (6): 1. `open_edit/render/emitter.py`, 2. `tests/test_render_emitter.py`, 3. Verification Commands Run & Outputs, Command:, Output:, Summary of Changes

### Community 174 - "Community 174"
Cohesion: 0.29
Nodes (6): 1. Observation, 2. Logic Chain, 3. Caveats, 4. Conclusion, 5. Verification Method, Handoff Report — Worker 1 Fix Agent (Milestone 1)

### Community 175 - "Community 175"
Cohesion: 0.29
Nodes (6): 1. Observation, 2. Logic Chain, 3. Caveats, 4. Conclusion, 5. Verification Method, Handoff Report — Milestone 1 (R1: Automatic 30ms Audio Micro-Fades in MLT Emitter)

### Community 176 - "Community 176"
Cohesion: 0.29
Nodes (6): 1. Observation, 2. Logic Chain, 3. Caveats, 4. Conclusion, 5. Verification Method, Handoff Report: Milestone 2 (R2: Token-Efficient Phrase-Packed Transcript Tool)

### Community 177 - "Community 177"
Cohesion: 0.29
Nodes (6): 1. Observation, 2. Logic Chain, 3. Caveats, 4. Conclusion, 5. Verification Method, Handoff Report — Milestone 3 (R3: Waveform Cut Inspection Image Generation)

### Community 178 - "Community 178"
Cohesion: 0.29
Nodes (6): 1. Observation, 2. Logic Chain, 3. Caveats, 4. Conclusion, 5. Verification Method, Handoff Report — Victory Auditor

### Community 179 - "Community 179"
Cohesion: 0.29
Nodes (6): 1. Observation, 2. Logic Chain, 3. Caveats, 4. Conclusion, 5. Verification Method, Handoff Report — worker_m4_fix

### Community 180 - "Community 180"
Cohesion: 0.29
Nodes (6): HyperFrames native guide, Native composition contract, Remotion migration, Render architecture, Route, Token rule

### Community 181 - "Community 181"
Cohesion: 0.29
Nodes (7): `audio_sync`, `black_frames`, Checks (and what to do about a failure), `duration`, `frozen_frames`, `overlays_burned`, `streams`

### Community 182 - "Community 182"
Cohesion: 0.29
Nodes (6): Capture confirmed hints, Do not, Read before planning, Reuse later, Style memory, When to load

### Community 183 - "Community 183"
Cohesion: 0.33
Nodes (4): get_pending_notes(), pyagent_get_pending_notes: returns pending notes for the project.  Per audit H3:, List pending notes. Default: first 10 full + count of rest., Resolve from a project path: the root itself or a file inside it.

### Community 184 - "Community 184"
Cohesion: 0.47
Nodes (5): _is_derivative(), list_assets(), Any, pyagent_list_assets: list all ingested assets in the project.  Exported as ``lis, Return ingested assets for the project.      By default **excludes** Remotion re

### Community 185 - "Community 185"
Cohesion: 0.33
Nodes (5): Current known issues (seed list), Delivery checklist (all must pass), Delivery Loop — Grok Orchestrator, Scope (do NOT change UI style), Worker protocol

### Community 186 - "Community 186"
Cohesion: 0.33
Nodes (5): Checklist, Current Status, Iteration Status, Notes & Findings, Progress Tracking — Open Edit Features

### Community 187 - "Community 187"
Cohesion: 0.33
Nodes (5): 1. `open_edit/serve/visual_verify.py`, 2. `tests/test_visual_verify_waveform.py` (New File), Changes Summary — Milestone 3 (R3: Waveform Cut Inspection Image Generation), Files Modified / Created, Test Verification Output

### Community 188 - "Community 188"
Cohesion: 0.33
Nodes (5): new_note_id(), new_version_id(), Shared id and timestamp generators.  Single source of truth for UUIDs and ISO-86, Return a fresh review-note id (``note_<hex12>``)., Return a fresh render-version id (``v_<hex12>``).

### Community 189 - "Community 189"
Cohesion: 0.47
Nodes (5): refreshTimeline(), normalizeEdits(), normalizeNotes(), normalizeTimeline(), summarizeOpPayload()

### Community 190 - "Community 190"
Cohesion: 0.40
Nodes (4): ingest_local(), Any, pyagent_ingest_local: ingest local media files into the project CAS.  Paths must, Ingest local files into ``.open_edit/assets``.      Args:         args: {

### Community 191 - "Community 191"
Cohesion: 0.40
Nodes (4): get_tool_schema(), Any, Hand-written function-calling schemas for the Open Edit agent tools.  These sche, Return the schema for a tool by name, or None if unknown.

### Community 192 - "Community 192"
Cohesion: 0.50
Nodes (5): refreshProjects(), renderProjectSelect(), selectProject(), clearChatLog(), disconnectWS()

### Community 193 - "Community 193"
Cohesion: 0.50
Nodes (3): Free-form script execution entry point (agent layer).  Task 2.3: moved from `ope, Run a free-form Python script in the sandbox and append its child ops.      Each, run_free_form_code()

### Community 194 - "Community 194"
Cohesion: 0.50
Nodes (3): capture_style_hint(), pyagent_capture_style_hint: persist a confirmed user style preference., Store a confirmed style hint (and optional pin) in the global profile.      ``pr

### Community 195 - "Community 195"
Cohesion: 0.50
Nodes (3): pyagent_run_python: invokes the Phase 3 free-form Python sandbox.  Per phase4-de, Run free-form Python; persist ops; return a slim summary by default., run_python()

### Community 196 - "Community 196"
Cohesion: 0.50
Nodes (3): pyagent_set_pinned_value: writes a pinned value to the style profile.  Per phase, Set pinned key=value in the global style profile., set_pinned_value()

### Community 197 - "Community 197"
Cohesion: 0.50
Nodes (3): Changes Summary - Milestone 2 (Token-Efficient Phrase-Packed Transcript Tool), Modified & Created Files, Test Output

### Community 198 - "Community 198"
Cohesion: 0.50
Nodes (3): Status, Step Log, Victory Auditor Progress

### Community 209 - "Community 209"
Cohesion: 0.67
Nodes (3): Raised by :func:`execute_tool` when the named tool is not     registered in ``op, ToolNotFound, LookupError

## Knowledge Gaps
- **616 isolated node(s):** `run_loop.sh script`, `projectRoot`, `compositionId`, `propsFile`, `output` (+611 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **64 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `EditGraphStore` connect `Community 1` to `Community 2`, `Community 3`, `Community 4`, `Community 140`, `Community 15`, `Community 17`, `Community 19`, `Community 20`, `Community 24`, `Community 26`, `Community 33`, `Community 36`, `Community 39`, `Community 44`, `Community 45`, `Community 54`, `Community 55`, `Community 195`, `Community 67`, `Community 71`, `Community 76`, `Community 209`, `Community 82`, `Community 83`, `Community 89`, `Community 103`?**
  _High betweenness centrality (0.154) - this node is a cross-community bridge._
- **Why does `render_project()` connect `Community 55` to `Community 0`, `Community 1`, `Community 2`, `Community 12`, `Community 13`, `Community 22`, `Community 24`, `Community 28`, `Community 31`, `Community 33`, `Community 36`, `Community 41`, `Community 43`, `Community 44`, `Community 48`, `Community 56`, `Community 60`, `Community 64`, `Community 68`, `Community 76`?**
  _High betweenness centrality (0.089) - this node is a cross-community bridge._
- **Why does `AssetStore` connect `Community 28` to `Community 32`, `Community 65`, `Community 33`, `Community 0`, `Community 41`, `Community 43`, `Community 13`, `Community 46`, `Community 83`, `Community 115`, `Community 55`, `Community 23`, `Community 24`, `Community 94`?**
  _High betweenness centrality (0.058) - this node is a cross-community bridge._
- **Are the 52 inferred relationships involving `EditGraphStore` (e.g. with `run_free_form()` and `_FlushingBuffer`) actually correct?**
  _`EditGraphStore` has 52 INFERRED edges - model-reasoned connections that need verification._
- **Are the 19 inferred relationships involving `Timeline` (e.g. with `ApplyError` and `_load_timeline()`) actually correct?**
  _`Timeline` has 19 INFERRED edges - model-reasoned connections that need verification._
- **Are the 29 inferred relationships involving `IR` (e.g. with `_StoreBuffer` and `AddClipOp`) actually correct?**
  _`IR` has 29 INFERRED edges - model-reasoned connections that need verification._
- **Are the 19 inferred relationships involving `RenderProfile` (e.g. with `PreviewVideoRenderer` and `PreviewVideoRequest`) actually correct?**
  _`RenderProfile` has 19 INFERRED edges - model-reasoned connections that need verification._