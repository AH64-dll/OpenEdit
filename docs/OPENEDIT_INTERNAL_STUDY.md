# OpenEdit Internal Study — hook points for new capabilities

> Deep technical map of the OpenEdit (Python `open_edit` package) codebase at
> `/home/amr/apps/mlt-pipeline`, written to let a different agent add:
> **auto color grading**, **filler-word / dead-space cutting**,
> **transcript-first editing**, and **better overlays** by porting
> mechanisms from browser-use / video-use.
>
> The Go/MLT legacy path under `cmd/`, `internal/`, `run.sh` is **out of
> scope and must be ignored**. All line numbers are approximate to the
> current tree (2026-08-04 snapshot) — re-grep before editing.

---

## 1. TRANSCRIPTION

### Backend
- **faster-whisper** (optional dependency), wrapped in
  `open_edit/storage/transcription.py`.
- `transcribe(src: Path, model_size: str | None = None, *, language: str | None = None) -> list[WordAlignment]`
  - Uses `WhisperModel(size, device="cpu", compute_type="int8")` and calls
    `model.transcribe(str(src), word_timestamps=True)` (+ `language=` when set).
  - Model size from `OPEN_EDIT_WHISPER_MODEL` (default `base`; `small` recommended for Arabic);
    language from `OPEN_EDIT_WHISPER_LANGUAGE` (unset = auto-detect).
  - **Swallows all failures** → returns `[]` (and logs a warning). One bad file never breaks a batch.
- **When it runs:** at ingest time only. `AssetStore.ingest_paths(...)` in
  `open_edit/storage/assets.py` calls `transcribe(src)` when the file has an
  audio stream and `do_transcribe=True` (default). There is **no
  re-transcribe / re-align tool** anywhere.

### Where the transcript is stored
- `WordAlignment` model in `open_edit/ir/types.py`:
  `{word: str, t_start: float, t_end: float, confidence: float = 1.0, speaker: Optional[str] = None}`.
- Stored on `Asset.alignment: list[WordAlignment]` and persisted in the asset
  sidecar JSON at `<project>/.open_edit/assets/<sha[:2]>/<sha>.meta.json`
  (written by `AssetStore.ingest_paths`).
- Loaded by `AssetStore.get(asset_hash)` / `list_assets_from_disk(project_path)`.

### The packed transcript (agent-facing format)
- `pack_transcript(alignment: list[WordAlignment], pause_threshold_sec: float = 0.5) -> str`
  in `open_edit/storage/transcription.py`. Phrase-packs words into Markdown:
  - `[MM:SS.ms - MM:SS.ms] [Speaker N] word word ...` (timestamp via `format_timestamp(seconds)`)
  - `*--- Silence (1.50s) ---*` inserted when inter-word gap `>= pause_threshold_sec`
  - New phrase on speaker transition (`word.speaker != phrase[0].speaker`).
- **Tool:** `get_transcript_packed` in `open_edit/agent/tools/pyagent_get_transcript_packed.py`
  - Args: `{"asset_hash": str, "pause_threshold_sec": float (opt, default 0.5)}`
  - Returns: `{"status": "ok", "asset_hash": ..., "transcript_packed": str}` (single field — deliberately avoids 3× token burn).
  - Returns `{"status": "retry", ...}` when the asset has no alignment yet (`require_alignment` in `agent/tools/_contract.py`).
- **MCP/query path:** `query_project {query: "get_transcript_packed", params: {asset_hash, pause_threshold_sec}}`
  → `kernel.tool_executor.execute_tool` → `kernel.pillar_tools.dispatch_query`
  → `TOOL_TABLE["get_transcript_packed"]` → the function above.

### What is MISSING vs “word-level + silence gaps + speakers”
| Needed | Status | Where it would go |
|---|---|---|
| Word-level timestamps | ✅ present (`WordAlignment`) | — |
| Per-word confidence | ✅ stored, **never used** | filter/propagate in pack or cuts |
| Silence gaps as **data** | ❌ implicit only — derived at pack time from inter-word gaps; **no persisted gap list**, no leading/trailing gaps in `pack_transcript` | add a `silence_gaps` field to `Asset`, or a derived store; `silence_cutter.find_silence_gaps` already computes them on demand |
| Speaker tags | ⚠️ field exists (`speaker`) but **`transcribe()` never populates it** — no diarization backend; packed output shows `[Speaker]` only if something fills it | wire a diarizer (e.g. pyannote) or leave speaker=source-audio-track id |
| Filler words | ❌ none — words are verbatim whisper tokens, no disfluency post-processing | new pass in `agent/skills/silence_cutter.py` (see §2) |
| Audio events (music/applause/laughter) | ❌ none | new event detector + a structured event list on `Asset` |
| Sentence/segment structure | ⚠️ only `analyze_narrative` (rule-based, `agent/skills/narrative_analyzer.py`) | — |

---

## 2. SILENCE CUTTING

### Two layers

**A. Suggest (read-only):** `edit_project generate=silence_cuts` →
`pyagent_propose_silence_cuts.propose_silence_cuts` → `open_edit/agent/skills/silence_cutter.py`:
- `find_silence_gaps(alignment, threshold_ms=400, duration=None, min_segment_s=0.0, keep_breath_ms=0) -> list[(start, end)]`
  — leading silence `[0, first_word.t_start]`, inter-word gaps `[prev.t_end, curr.t_start]`,
  trailing silence `[last.t_end, duration]`; merges gaps separated by speech `< min_segment_s`.
- `propose_cuts(asset, silence_threshold_ms=400, min_segment_s=2.0, keep_breath_ms=600) -> list[{"t_start", "t_end", "suggested_kind": "trim"}]`.
- `no_word_split_check(asset, t_start, t_end, tolerance_ms=50) -> (passed, detail)`
  — **word-boundary safety check exists** (a cut is bad if it splits a word).
  ⚠️ It is **not called** by `apply_silence_gaps`; it is only re-exported via `qc/gate.py` and tested.
- With `compress: true`, `propose_silence_cuts` also runs
  `render/silence_compress.compress_silence` on the asset and ingests the trimmed file as a new CAS asset (`compressed_asset_hash`).

**B. Apply (mutating):** `edit_project operation=apply_silence_gaps` →
`pyagent_timeline_ops.apply_silence_gaps` (`open_edit/agent/tools/pyagent_timeline_ops.py`):
- Args: `{"clip_id": str, "gaps": [{"t_start","t_end"} | pairs | {"start_sec","end_sec"}]}`.
- `_normalize_gaps` → `_keep_ranges(in_point, out_point, gaps)` inverts gaps into keep ranges inside the clip.
- Appends **`RemoveClipOp` + one `AddClipOp` per keep segment**, laid sequentially from `clip.position_sec`.
  Returns `{"status":"ok","kind":"apply_silence_gaps","removed_clip_id","new_clip_ids","keep_count"}`.
- This is a **pure IR edit** — the render pipeline downstream never re-detects silence.

### render/silence_compress.py (standalone compression path)
- `compress_silence(input_path, output_path, *, max_silence_s=0.2, threshold_db=-35.0, detect_min_s=0.2, audio_only=False, gaps=None)`
  - With `gaps=` provided → **skips ffmpeg detection** and uses those spans (this is how word-alignment cuts are wired in).
  - `build_keep_ranges(duration, silences, max_silence_s)` keeps the **last `max_silence_s` seconds of each silence** as padding (default 200 ms) — this is the existing “cut padding”.
  - `_concat_ranges` → writes an ffconcat list (inpoint/outpoint) and runs `ffmpeg -f concat -c copy` (stream copy, fast, no mega-filter_complex).
  - Returns stats `{ok, changed, input/output_duration_s, silence_count, segment_count, removed_s, elapsed_s, concat_elapsed_s}`.
- `detect_silence_spans(path, threshold_db=-35.0, min_s=0.2, start_sec, end_sec)` in `render/ffmpeg_probe.py` (ffmpeg `silencedetect`).

### Where new capabilities hook in
- **Filler-word removal:** (1) detection — add a filler pass to `silence_cutter.py` that scans `asset.alignment` for disfluency tokens (e.g. `um`, `uh`, `like`, `you know`) and emits them as gap-like spans (optionally using `confidence` to avoid false positives); (2) application — `apply_silence_gaps` already accepts **arbitrary gaps**, so filler spans can be fed straight in via the existing op, or a new `apply_filler_removal` wrapper in `pyagent_timeline_ops.py` that merges filler spans with silence gaps before calling the same `_keep_ranges` logic.
- **Cut padding / word-boundary snapping:** lives in `_keep_ranges` / `apply_silence_gaps`
  (`pyagent_timeline_ops.py`) and/or the merge step of `find_silence_gaps`. Use `no_word_split_check`
  (already implemented, currently unused) to snap each keep-range edge to the nearest valid word
  boundary; the `max_silence_s`-style padding logic in `silence_compress.build_keep_ranges` is the
  numeric precedent (keep 200 ms of breathing room at each edge).

---

## 3. COLOR GRADING

### Does any exist? **No.**
Repo-wide grep for `eq=`/`colorbalance`/`curves`/`grade`/`lut`/`colortemperature`/`colorchannelmixer`/`hue` finds **no production color-grading code**. The closest primitives are four catalog effects (plain MLT filters, single-param):
- `open_edit/ir/catalog/effects/brightness.yaml` → `mlt_service: brightness`, param `value ∈ [-1,1]`
- `contrast.yaml`, `saturation.yaml` (value ∈ [0,2]), `luma.yaml` (softness/invert).
- `open_edit/ir/catalog/effects/eq.yaml` is an **audio** parametric EQ (`mlt_service: equalizer`).

### How an effect reaches ffmpeg today (the hook you need)
`AddEffectOp` (target `clip` or `track`) is already a first-class IR op. Full data flow:

1. `edit_project operation=add_effect` (or `run_script` → `ir.add_effect(...)`, or `apply_generated_ops`) appends
   `AddEffectOp{target_kind, target_id, effect_type, params}` via `EditGraphStore.append`
   (`open_edit/storage/edit_graph.py`) — which **validates against the YAML catalog**
   (`open_edit/ir/validate.py` ~line 158: unknown `effect_type` → error listing `catalog.known_names()`;
   also checks `target_kind` against `spec.target_kind`).
2. `derive_timeline(project)` (`open_edit/ir/derive.py`) replays ops with
   `apply_operation` (`open_edit/ir/apply.py` → `_apply_add_effect` in `open_edit/ir/apply_effects.py` ~line 290),
   attaching an `Effect{effect_id, effect_type, params, keyframes}` to `clip.effects` or `track.effects`.
3. `orchestrator.render_project` (`open_edit/render/orchestrator.py`) → `build_render_plan`
   (`open_edit/render/timeline_plan.py`) → `emit_timeline` (`open_edit/render/emitter.py`).
4. `emitter._emit_filter(parent, effect, fps_num, fps_den)` emits
   `<filter id="..." service="{effect.effect_type}">` with one `<property name="...">` per param
   and `<kf frame value interp>` per keyframe — **inside the `<playlist><entry>` for a clip**
   (clip effects) or on the `<playlist>` element (track effects). Transitions (`effect_type` prefixed
   `transition_`) become `<transition service=...>`.
   ⚠️ So an effect is rendered iff it is a valid **MLT filter service** name — the catalog YAML’s
   `mlt_service` field is the mapping layer.
5. The MLT XML is rendered by melt (`build_pipe_commands` in `open_edit/render/pipe_builder.py`:
   `melt <xml> -consumer avformat:pipe: f=rawvideo ...` piped to ffmpeg) → final mp4.

### Exact hook for a per-segment auto-grade
- **Recommended (IR-level, matches existing architecture):**
  1. Add a catalog entry, e.g. `open_edit/ir/catalog/effects/color_grade.yaml`
     with `name: color_grade`, `mlt_service: colorbalance` (MLT’s native color-balance filter; params
     like `shadow_rd`/`mid_gn`/`highlight_bl` etc. — MLT property names go 1:1 into the emitted `<property>`),
     or `frei0r.*`/`avfilter` services if MLT loads them. Validation and emission then work with **zero code changes**.
  2. Add a tool `auto_color_grade(args, project_path)` in `open_edit/agent/tools/pyagent_timeline_ops.py`
     that (a) reads the target clip(s) — pattern: `load_project` + `derive_timeline` like `apply_silence_gaps`;
     (b) computes per-segment params (from histogram probes or a style profile — see §8);
     (c) appends one `AddEffectOp` per clip with `effect_type="color_grade"`.
  3. Register the tool in `agent/tools/__init__.py` (`TOOL_TABLE` + `__all__`) and in
     `kernel/pillar_tools.py` `_EDIT_ROUTING["auto_color_grade"] = "auto_color_grade"`.
  4. Add the new effect name to `_VIDEO_EFFECT_NAMES` in `open_edit/render/preview_invalidation.py`
     (~line 447, currently `{"blur","brightness","chroma","color","composite","contrast","crop","opacity","overlay","saturation","transform","video"}`)
     so preview-chunk fingerprints invalidate when the grade changes.
  5. Optionally a standalone op `AutoColorGradeOp` (new kind) if you want one graph op that expands to many
     clip effects at apply time — then you must also add a branch in `open_edit/ir/apply.py` `apply_operation`
     and validation in `validate.py` (see §5 for the full file-by-file checklist).
- **Alternative (global/whole-frame):** inject ffmpeg filters in `pipe_builder.overlay_filter_chain` /
  `build_pipe_commands` (the ffmpeg `-filter_complex` stage). Only sensible for whole-timeline looks;
  per-segment would need `enable='between(t,..)'` windows and does not flow through the IR/undo graph.

---

## 4. RENDER PIPELINE (IR op → mp4)

### End-to-end
```
MCP: trigger_render {mode: proxy|final|overlay|preview-chunks}
 → kernel/tool_executor.execute_trigger_render
 → kernel/render_jobs.RenderJobService.enqueue(project, mode, encoder_backend, params)
 → _run/_launch: subprocess  python -m open_edit.cli render --mode <mode> --json   (cwd = project root)
 → cli.cmd_render
 → render/orchestrator.render_project(project_id, project_dir, workdir=project/.open_edit/renders, mode, ...)
```
`render_project` stages (in order):
1. `EditGraphStore(db).load_all()` → keep `status=="applied"` ops → `Project` → `derive_or_load_timeline(project, store, strict=True)` (`storage/timeline_cache.py`, snapshot-cached by `compute_edit_graph_hash`).
2. **Deliverable cache** lookup: `RenderCache(workdir/render_cache)`, key = `render_cache_key(graph_hash, profile_fingerprint, content_fingerprint)`; content fingerprint includes Remotion `render_reference_fingerprint` + HyperFrames `hyperframes_reference_fingerprint`. Cache hit → early return.
3. **Overlay/composition materialization** (only if present):
   - `materialize_hyperframes_overlays(timeline, project_dir, mode, width, height, fps)` (render/hyperframes.py) → HTML overlay MOV, appended to `plan.overlay_clips` as `OverlayClip(position_sec=0, duration_sec=timeline.duration, label="hyperframes", alpha=True)`.
   - `materialize_remotion_compositions(...)` (render/materialize.py) → CAS clips (legacy path).
4. `build_render_plan(timeline, ops, AssetStore, mode, frame_engine, frame_profile, emission_profile)` (render/timeline_plan.py) → `RenderPlan{melt_timeline, overlay_clips, asset_paths, emission_profile, source_media_policy, ...}`. `timeline_for_melt()` strips Remotion/upper video tracks (they are burned as ffmpeg overlays, not melt multitrack).
5. `emit_timeline(plan.melt_timeline, EmitterConfig(profile=...), asset_paths, hwaccel)` → MLT XML written to `workdir/project_<graph_hash[:12]>.mlt`.
6. `spec = resolve_encoder_args(profile, encoder_backend)` (render/encoder.py: NVENC/QSV/AMF/VAAPI or libx264, quality tiers) → `build_pipe_commands(melt_bin, xml, output_mp4, profile, spec, plan.overlay_clips, ...)` (render/pipe_builder.py) → `PipeCommands{melt_video_cmd, melt_audio_cmd, ffmpeg_cmd}`:
   - melt video: `melt xml -consumer avformat:pipe: f=rawvideo vcodec=rawvideo pix_fmt=nv12 s=WxH frame_rate_num/den ...`
   - melt audio: separate `-consumer avformat:<stem>.audio.wav video_off=1 format=wav`
   - ffmpeg: rawvideo pipe + wav + overlay inputs → `-filter_complex overlay_filter_chain(...)` (per-overlay `scale→format=rgba→setpts→overlay=enable='between(t,...)'`, optional blur-under) → `-map [vout] -map 1:a?` → `-c:v <vcodec> <ffmpeg_args> -c:a aac` → **`workdir/project_<graph_hash[:12]>.mp4`** (i.e. `<project>/.open_edit/renders/project_<hash>.mp4`).
   - CUDA fast path (`run_cuda_fastpath`) is used instead when `hwaccel_on` and no overlays and `timeline_supports_cuda_fastpath`.
7. `run_pipe` (render/melt_runner.py) → on success `source_repair.repair_render_output` (black/frozen-frame repair for whole-file emissions) → `cache.put` → `record_snapshot` → `RenderResult{ok, output_path, mode, profile, duration_sec, elapsed_sec, cache_hit, edit_graph_hash, diagnostics}`.
8. Back in `render_jobs._run`: `_attach_qc` runs `qc.gate.run_qc_gate` on the mp4 and attaches `qc_report` to the durable job row/result.

### Where per-segment audio/video filters attach
- **Per clip:** `clip.effects` → `emitter._emit_filter` → `<filter>` **inside the `playlist/entry`** (video and audio both; audio gets automatic 30 ms volume micro-fades via `_emit_audio_micro_fade` first).
- **Per track:** `track.effects` → `<filter>` on the `playlist` element.
- **Per segment via ffmpeg:** `pipe_builder.overlay_filter_chain` (overlay burn windows, `enable='between(t,...)'`).
- **Global encode:** `encoder.py` `EncoderSpec` (melt args / ffmpeg args) and `profiles.py` `RenderProfile`.

---

## 5. MCP TOOL SURFACE

### The 6 tools
`query_project`, `edit_project`, `run_script` (the 4 pillars) + `get_render_job`, `cancel_render_job` (helpers). Registered/validated/dispatched in exactly these places:

| File | Role |
|---|---|
| `kernel/tool_registry.py` | `TOOL_REGISTRY: dict[str, type[BaseModel]]` (Pydantic arg models: `QueryProjectArgs`, `EditProjectArgs`, `RunScriptArgs`, `TriggerRenderArgs`, `GetRenderJobArgs`, `CancelRenderJobArgs`), descriptions, `build_tool_schemas()` → Anthropic-shaped schemas. |
| `kernel/tool_schemas.py` | `TOOL_SCHEMAS = build_tool_schemas()`; `TOOL_BY_NAME`; `get_tool_schema`; `TOOL_USAGE_GUIDE`; `IR_MODEL_SUMMARY` (embedded in system prompt). |
| `kernel/schema_validator.py` | `validate_or_error(name, args)` — hand-rolled (no jsonschema): required fields, `additionalProperties:false`, shallow types. |
| `kernel/tool_executor.py` | `execute_tool(name, args, project_path, command_id)` — strips injected `project_id`, validates, idempotency cache via `CommandStore` (`_cached_done_result`/`_record_done_command`), then: render helpers inline; `query_project`→`pillar_tools.dispatch_query`; `edit_project`→`dispatch_edit`/`dispatch_generate`; everything else → `agent.tools.TOOL_TABLE`. `execute_trigger_render` is the async virtual tool. `_KERNEL_HANDLED_TOOLS` pins the 5 names that must NOT be in TOOL_TABLE (completeness test in `tests/test_tool_registry.py`). |
| `kernel/pillar_tools.py` | Routing dicts `_QUERY_ROUTING` (6 queries), `_EDIT_ROUTING` (13 operations), `_GENERATE_ROUTING` (7 kinds) → TOOL_TABLE names; `dispatch_query/dispatch_edit/dispatch_generate`; `_apply_generated_ops` (validates each op dict via `TypeAdapter(OperationUnion)` and appends atomically). |
| `agent/tools/__init__.py` | The single canonical `TOOL_TABLE: dict[str, Callable]` (28 entries) + `__all__`. Each tool fn is `fn(args: dict, project_path: str|Path) -> dict` decorated with `@tool_result` (`agent/tools/_contract.py`: `{"status":"ok"|"error"|"retry"}` normalization). |
| `mcp/adapters.py` | `dispatch_mcp_tool(name, arguments, project_path)` — trigger_render / get_render_job / cancel_render_job branches, then `execute_tool` for registry tools; `mcp_tool_schemas()`; `result_to_json`. |
| `mcp/server.py` | `build_server(project_path)` — `list_tools` from `mcp_tool_schemas()`, `call_tool` → `dispatch_mcp_tool` → `TextContent(result_to_json(result))`; also resources (`open-edit://skills/*`) and prompts. |
| `mcp/skills.py` | Skill markdown loading (`SKILL_FILES`, `MCP_SKILL_STEMS`, `load_skill`, `mcp_instructions`) from `skills/` (canonical) or `open_edit/harness_skills/` (packaged). |

### EXACT minimal steps to add a new operation, e.g. `operation=auto_color_grade`
1. **`open_edit/ir/types.py`** — define `AutoColorGradeOp(Operation)` (`kind: Literal["auto_color_grade"] = "auto_color_grade"`, fields e.g. `target_kind/target_id` or `scope: "project"|"clip"`, `params: dict`) and add it to the `OperationUnion` discriminated union.
   *(If instead you reuse `AddEffectOp` + a catalog YAML — the simpler path described in §3 — skip steps 1–2.)*
2. **`open_edit/ir/apply.py`** — add an `if isinstance(op, AutoColorGradeOp): return _apply_auto_color_grade(timeline, op, strict=strict)` branch (implement the helper in `open_edit/ir/apply_effects.py`, e.g. expanding to one `Effect` per clip).
3. **`open_edit/ir/validate.py`** — add a validation branch (reference checks for `target_id`; keep the free-form ops pattern in mind — new structured ops get reference validation).
4. **`open_edit/ir/api.py`** — add `IR.auto_color_grade(...)` if `run_script` users should build it.
5. **`open_edit/agent/tools/pyagent_timeline_ops.py`** — add `@tool_result def auto_color_grade(args, project_path)` (use `make_ir(project_path)` to append the op; pattern: `add_clip`/`apply_silence_gaps`).
6. **`open_edit/agent/tools/__init__.py`** — import + add to `__all__` and `TOOL_TABLE` (`"auto_color_grade": auto_color_grade`).
7. **`open_edit/kernel/pillar_tools.py`** — `_EDIT_ROUTING["auto_color_grade"] = "auto_color_grade"`.
8. **`open_edit/kernel/tool_registry.py`** — extend `_EDIT_PROJECT_DESC` text. (Schema change NOT required for new operations: `EditProjectArgs.operation` is `Optional[str]`.)
9. **Render integration** — if the op adds catalog effects: nothing in the emitter (generic `_emit_filter`); update `preview_invalidation.py` effect-name sets; extend the fingerprint if the op changes render output directly.
10. **Tests** — see §9; minimum: catalog test (if YAML), IR apply test, emitter XML test, pillar routing test, tool-table completeness stays green (`tests/test_tool_registry.py` asserts every schema name is in TOOL_TABLE or `_KERNEL_HANDLED_TOOLS`, and `test_tool_table_entries_all_callable`).

### To add a new **query** (e.g. `get_timeline_view`, `get_silence_gaps`)
1. `tool_registry.py`: add the name to the `Literal[...]` of `QueryProjectArgs.query` **and** mention in `_QUERY_PROJECT_DESC`.
2. `agent/tools/pyagent_<name>.py`: new `@tool_result` fn (canonical error/retry shapes from `_contract.py`).
3. `agent/tools/__init__.py`: export + `TOOL_TABLE`.
4. `kernel/pillar_tools.py`: `_QUERY_ROUTING["get_timeline_view"] = "get_timeline_view"`.
5. Tests: `tests/test_pillar_tools.py` (dispatch hit), schema enum test, fn-level test.
(Same pattern for a new `generate=` kind via `_GENERATE_ROUTING`.)

---

## 6. VISUAL VERIFY

### What `open_edit/serve/visual_verify.py` does TODAY
It is an **LLM visual-verification harness** for post-render review, not a timeline tool:
- `sample_frames(duration_s, override_count)` — tiered frame timestamps (1→1, 30→3, 120→4, else 5 frames at 10–90%).
- `encode_jpeg(input_path, output_path, max_edge_px, jpeg_quality, max_bytes)` — ffmpeg single-frame JPEG extraction (downscaled, retry at half size).
- `model_capability(model_id, models_store_path)` — reads `~/.pi/agent/models-store.json` for image support.
- `build_verification_tool_result(render_output, frames, capability, mode)` — assembles `trigger_render` result with `verification: {verdict_required, frames[], qc_evidence, prompt}`; `build_qc_evidence(qc_report, duration_s)` folds the deterministic QC spans into the prompt; `_verification_prompt` demands a `VERIFICATION: PASS|FAIL|UNCERTAIN` line.
- `parse_verdict(text)`, `prune_images(history, last_verdict, keep_last_n)` — history hygiene.
- **The waveform capability is GONE from production.** `generate_waveform_inspection_image` (video frame + `showwavespic` vstack/hstack with a red cut marker) was **deleted** in the 7.1 restructure (see `docs/superpowers/plans/2026-07-31-open-edit-restructure.md` line ~502: “delete `generate_waveform_inspection_image` … verified test-only”). It survives only as a **local copy inside `tests/test_visual_verify_waveform.py`** (with its `_probe_streams` helper) — the exact ffmpeg filter recipe for filmstrip+waveform+marker is right there: `[0:v]select…pad[vid];[0:a]showwavespic=s=…:colors=…[wave];[wave]drawbox=x=<marker>:…[wave_marked];[vid][wave_marked]vstack|hstack=2[out]` with `-ss/-t` windowing around `cut_time_sec`.

### Distance to video-use’s `timeline_view` composite (filmstrip + waveform + word labels PNG for arbitrary time range)
- **Not close today.** No function composites a PNG timeline view; the review UI (`open_edit serve`) renders an interactive timeline in browser JS, and `preview-chunks` produce mp4 chunks, not composite images.
- **Everything needed exists as building blocks:** ffmpeg `showwavespic` recipe (test file), frame extraction (`encode_jpeg` / `qc/thumbnail.get_thumbnail`), word-level alignment with timestamps (`Asset.alignment`), arbitrary ranges (`-ss/-t` + `qc/*` detectors already take `in_sec/out_sec`), and a clean surface to add it as a **new query** (e.g. `query_project query=get_timeline_view {asset_hash|project, start_sec, end_sec, width}` → `pyagent_get_timeline_view.py` per §5, rendering a PNG with ffmpeg drawtext/drawbox word labels; serve it through the existing static-file/asset routes). No render-job machinery needed — it is a read-only query.

---

## 7. OVERLAYS

### What exists
**Native HyperFrames path (current, preferred):**
- **IR:** `AddHtmlOverlayOp` / `RemoveHtmlOverlayOp` (`ir/types.py`); `Timeline.overlays: list[HtmlOverlay]` (`overlay_id, template_path, variables, position_sec, duration_sec`). Applied in `ir/apply.py` (append+sort). Agent tool: `edit_project operation=add_hyperframes_overlay` → `pyagent_timeline_ops.add_hyperframes_overlay` (validates `template_path` stays inside project; requires the file to exist).
- **Materialization:** `open_edit/render/hyperframes.py`:
  - `hyperframes_reference_fingerprint(timeline, project_path, mode, width, height, fps)` — SHA-256 of the generated composition HTML + render spec (this is the cache/fingerprint hook: **any new overlay parameter must flow through `generate_composition_html` to invalidate caches**).
  - `materialize_hyperframes_overlays(timeline, project_path, mode, width, height, fps, force)` → composition HTML → `render_overlay_layer` (hyperframes CLI, `--format mov -q standard --strict`) → cached at `<project>/.open_edit/hyperframes/out/<mode>/overlay_<content_hash[:24]>.mov` (LRU eviction, `OPEN_EDIT_HYPERFRAMES_CACHE_MAX_BYTES` default 512 MB; binary from `OPEN_EDIT_HYPERFRAMES_BIN` or `node_modules/.bin/hyperframes`, timeout `OPEN_EDIT_HYPERFRAMES_TIMEOUT_SECONDS` default 3600).
- **HTML generation:** `open_edit/render/html_overlay.py`:
  - `generate_composition_html(timeline, project_workdir, render_spec)` — resolves `template_path` (project-relative, then built-in `open_edit/render/templates/overlay/` — currently only `lower_third.html`), inlines `{{key}}` variables (`_inline_variables`, primitives only, `html.escape`), assigns non-overlapping tracks (`_assign_tracks`), emits clip `<div class="clip" data-start data-duration data-track-index>` inside a `data-no-timeline` root (`data-width/height/fps/duration`). Templates may also use `class="clip"` children and `window.__timelines` for seekable animation (see `skills/hyperframes_native.md`).
  - `render_overlay_layer(comp_html_path, output_path, render_spec, should_cancel)` — hyperframes subprocess wrapper.
  - `composite_with_background(bg_path, overlay_path, output_path, render_spec, should_cancel)` — ffmpeg `[0:v][1:v]overlay=eof_action=pass`, `-map 0:a -map [outv] -c:a copy`.
  - `render_composited(timeline, project_workdir, render_spec, bg_renderer, should_cancel)` — async 4-stage orchestrator (bg render ∥ HTML gen → overlay render → composite), TaskGroup cancellation.
- **Flow into a render:** (a) native path — orchestrator calls `materialize_hyperframes_overlays`, appends result as `OverlayClip(label="hyperframes", alpha=True)` covering the whole timeline, and `pipe_builder.overlay_filter_chain` burns it in the ffmpeg `-filter_complex` stage of proxy/final/preview-chunk renders; (b) legacy `mode=overlay` — `kernel/render_overlay.run_trigger_render` → `html_overlay.render_composited` with `bg_renderer=lambda: _run_mlt_only_render(...)`.

### What’s missing vs video-use parallel-subagent animation generation
- **No LLM-driven animation generation.** Overlays are authored as static HTML templates + primitive `variables`; there is no pipeline that spawns a subagent to design/animate an overlay per segment, no prompt→HTML generation service, no per-frame JS animation authored by the agent (only whatever a human writes in the template + `window.__timelines`).
- **No parallelism:** one sequential hyperframes CLI render per overlay layer; video-use-style “parallel subagents each render an animation” would map to parallel `render_overlay_layer` calls (or a new host worker) writing separate overlay MOVs, then one ffmpeg composite — the composite/OverlayClip seams (`plan.overlay_clips` + `overlay_filter_chain`) already support **multiple** ordered overlays.
- **Variables limited to primitives** (`_inline_variables` raises on dict/list/None) — JSON payloads (e.g. caption arrays, keyframed motion paths) would need a new mechanism (e.g. `window.__open_edit_vars` injection as JSON script tag — the `AddHtmlOverlayOp` docstring mentions it but the current generator only does `{{key}}` string replacement).
- **Templates:** only one built-in (`lower_third.html`); no built-in caption/branding/scoreboard set.

---

## 8. QC + STYLE MEMORY

### What `qc/gate.py` does automatically
`run_qc_gate(video_path, output_thumb_dir, *, target_duration_s, mode, source_baseline, policy) -> QCReport` runs **10 checks**:
`render_completed`, `proxy_render`, `streams` (≥1 video + ≥1 audio), `duration` (within ±1.0 s of target), `audio_sync` (≤200 ms), `black_frames` (`qc/black_frames.py`, blackdetect, source-known spans excluded), `frozen_frames` (`qc/frozen_frames.py`, freezedetect, min 1.0 s), `silence` (`qc/silence.py`, silencedetect @ -35 dB / 1.0 s), `overlays_burned` (informational — no OCR), `thumbnail` (`qc/thumbnail.py`, JPEG at t=0).
- **Attached automatically** by `render_jobs._attach_qc` after every successful render (`qc_report` on the job + `diagnostics["qc_report"]`); never flips job status (diagnostic only). The CLI also runs it and exits 1 on failure.
- **Policy** (`qc/policy.py`): `resolve_qc_policy(render_mode, cache_hit)` → `skip|light|full`; proxy cold=`light` default, warm cache=`skip`, final/overlay=`full` with `OPEN_EDIT_FINAL_QC_BUDGET_SEC` (900 s) and `OPEN_EDIT_QC_BLACKDETECT_MAX_SEC`; env knobs `OPEN_EDIT_PROXY_QC_MODE` / `OPEN_EDIT_PROXY_WARM_QC_MODE` / `OPEN_EDIT_PROXY_QC_POLICY`.
- **Spans output:** `QCReport.spans = {black_frames[], silence[], frozen_frames[]}` — consumed by `visual_verify.build_qc_evidence` (the LLM sees them as ground truth).

### What style memory stores
- File: `~/.open-edit/style_profile.json` (**user-global, not per-project**; `open_edit/storage/config.py` `_default_profile()`), managed by `open_edit/style/aggregate.py`:
  - categories: `transitions, fades, pacing, color, audio, text_captions, visual_treatment, structure, export, corrections` (each `{preferred/avoid/default_duration_s/tendency/…, confidence, examples}`), plus `pinned` (key→value) and `hints` (last 50).
  - `set_pinned(key, value)` and `capture_hint(category, hint, key, value, source)` — the `capture_style_hint` tool requires `confirmed: true`.
- Read path: `open_edit/style/retrieve.py` `get_slice(op_type)` — tag-gated via `TAG_MAP` (e.g. `AddEffect → ["fades","color","visual_treatment","corrections"]`), confidence threshold 0.2, 250-token cap; `get_style_profile` tool → `query_project query=get_style_profile {op_type}`.
- Injection: `open_edit/agent/style_inject.py` `build_prior_state(...)` builds the `<prior_state>` system-prompt block (creativity, style slice, pins, latest 3 ops, pending notes).

### Where an auto-color-grade style profile belongs
- **Category:** the existing `color` category (`tendency`, `confidence`, `examples`) is the natural home; `TAG_MAP` already routes `AddEffect` slices to it.
- **Pins:** `pinned["color.saturation"]`, `pinned["color.temperature"]`, `pinned["color.contrast"]`, `pinned["color.lut"]` (path to a LUT in the project) — read by the `auto_color_grade` tool via `style.retrieve.get_slice("AddEffect")` + `pinned`, same pattern as `edit-planning.md` honoring pins.
- The profile is user-global; per-project grade prefs can go in `EditGraphStore.set_project_meta_field(key, value)` (SQLite `project_meta` table) if needed.

---

## 9. TEST CONVENTIONS

- **Layout mirrors the package:** `tests/test_ir/`, `tests/test_render/`, `tests/test_qc/`, `tests/test_storage/`, `tests/test_style/`, `tests/test_skill/`, plus flat files (`test_pillar_tools.py`, `test_tool_registry.py`, `test_transcription_pack.py`, `test_silence_compress.py`, `test_html_overlay.py`, `test_visual_verify_waveform.py`, …).
- **`tests/conftest.py`:** inserts repo root on `sys.path`; fixtures:
  - `tmp_notes_db` — isolated `NotesStore` under `tmp_path`.
  - `tmp_project_with_assets` — seeds a CAS asset (bare file + `.meta.json` sidecar) and an `AddClipOp` in a real `EditGraphStore` so `run_free_form`/tools can discover it.
- **Media fixtures (`testdata/`):** deterministic synthetic clips with regenerate commands in `testdata/README.md`: `clip_short.mp4` (10 s 1920×1080, 2 scene cuts, no audio), `video_with_audio.mp4` (3 s 320×240 + 440 Hz sine), and `tests/testdata/raw_videos/clip_a|b|c.mp4` (2 s 320×240 h264, no audio) used by CLI/e2e/storage/qc/render tests.
- **Golden files:** `tests/testdata/golden_11clip/edit_graph.json` + `expected_timeline.json`; `tests/test_render/test_golden_fixtures.py` derives the timeline and compares byte-for-byte (regeneration command in README).
- **Unit-test style:** mock everything external — `patch("open_edit.storage.transcription.WhisperModel", ...)`, `patch("...detect_silence_spans")`, `patch("..._concat_ranges")`, `mock.patch("shutil.which", return_value=None)`; real-ffmpeg tests use `pytest.mark.skipif(not shutil.which("ffmpeg"), ...)` (see `tests/test_qc/test_gate.py`); MLT XML assertions parse with `lxml.etree` and inspect `<filter>/<kf>` attributes (see `tests/test_render_emitter.py`); tool-level tests call the TOOL_TABLE function directly with a `tmp_path` project and assert the canonical `{"status": "ok"|"error"|"retry"}` envelope (see `tests/test_transcription_pack.py`); subprocess wrapper modules are tested with mocked Popen + exact-command assertions (see `tests/test_html_overlay.py`).
- **Registry pinning:** `tests/test_tool_registry.py` pins `len(TOOL_SCHEMAS) == 6`, schema names, `additionalProperties:false`, the `_KERNEL_HANDLED_TOOLS` disjointness, and `len(TOOL_TABLE) >= 26` — new tools must keep these green.
- **New-feature test checklist (matching existing practice):** catalog YAML load test (`tests/test_ir/test_catalog.py`), IR apply/derive test, emitter XML test (filter service + params + keyframes), pillar dispatch test (`tests/test_pillar_tools.py`), tool contract test, `TOOL_TABLE`/schema pinning tests, and — for anything touching render — a `build_pipe_commands`/fingerprint test (`tests/test_render/test_pipe_builder.py`).

---

## Quick-reference: capability → primary hook

| New capability | Primary hook | Secondary hooks |
|---|---|---|
| Auto color grading | new catalog YAML `ir/catalog/effects/color_grade.yaml` + `auto_color_grade` tool in `pyagent_timeline_ops.py` emitting `AddEffectOp`s | `pillar_tools._EDIT_ROUTING`, `preview_invalidation._VIDEO_EFFECT_NAMES`, style `color` category |
| Filler-word cutting | extend `agent/skills/silence_cutter.py` (filler spans) → feed into existing `apply_silence_gaps` `gaps` param | `no_word_split_check` snapping in `_keep_ranges`/`apply_silence_gaps`; `silence_compress.build_keep_ranges` padding |
| Transcript-first editing | `query_project get_transcript_packed` already exists; add `Asset.silence_gaps`/speaker/diarization + new queries (`get_timeline_view`, `get_silence_gaps`) | `WordAlignment.speaker` population; `transcription.pack_transcript` extension |
| Better overlays | `html_overlay.generate_composition_html` (JSON vars, more templates), parallel `render_overlay_layer` calls into `plan.overlay_clips` | `hyperframes_reference_fingerprint` (cache invalidation), `pipe_builder.overlay_filter_chain` |
| Timeline-view composite (video-use parity) | new query tool `pyagent_get_timeline_view.py` reusing the deleted recipe in `tests/test_visual_verify_waveform.py` | `serve/routers/*` static file serving |
