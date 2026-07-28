# Handoff Report: Milestone 2 (R2: Token-Efficient Phrase-Packed Transcript Tool)

## 1. Observation
1. **`open_edit/storage/transcription.py` (lines 1-51)**: Contains `transcribe(src: Path, model_size: str = "base") -> list[WordAlignment]`, which calls `faster_whisper` to output word alignments.
2. **`open_edit/ir/types.py` (lines 79-84, 86-105)**: Defines `WordAlignment(word: str, t_start: float, t_end: float, confidence: float = 1.0)` and `Asset(alignment: list[WordAlignment] = Field(default_factory=list))`.
3. **`open_edit/storage/assets.py` (lines 134-152, 155-175)**: `AssetStore.ingest_paths()` runs `transcribe()` for media with audio and saves metadata into `<hash>.meta.json` sidecar files.
4. **`open_edit/agent/tools/__init__.py` (lines 14-52)**: Re-exports all agent tools (`add_marker`, `list_assets`, `propose_silence_cuts`, etc.) in `__all__` so `getattr(open_edit.agent.tools, name)` can dispatch them.
5. **`open_edit/serve/tool_registry.py` (lines 48-60)**: Defines `QueryProjectArgs` with `query: Literal["list_assets", "get_pending_notes", "get_style_profile", "analyze_narrative", "search_assets"]`.
6. **`open_edit/serve/pillar_tools.py` (lines 13-35)**: Defines `dispatch_query(query: str, params: dict, project_path: Path)` which routes query names to functions imported from `open_edit.agent.tools`.
7. **`open_edit/serve/tool_schemas.py` (lines 55-80)**: Contains `TOOL_USAGE_GUIDE` system prompt documentation listing available query modes under `query_project`.

---

## 2. Logic Chain
1. From Observation 1 & 2, `faster-whisper` produces fine-grained word alignments (`WordAlignment`) stored in `Asset.alignment`.
2. From Observation 3, asset transcript alignments are persisted in `<hash>.meta.json` sidecar files, accessible via `get_asset_store(project_path).get(asset_hash)`.
3. Converting raw `WordAlignment` lists into a Markdown format (`takes_packed.md`) requires grouping words by speaker and inter-word pause thresholds (`curr.t_start - prev.t_end >= pause_threshold_s`), formatting timestamps into `[MM:SS.ss - MM:SS.ss]`, and inserting silence gap markers `*--- Silence (<gap:.2f>s) ---*`.
4. From Observation 4, 5, 6 & 7, registering the new `get_transcript_packed` tool requires:
   - Creating `open_edit/agent/tools/pyagent_get_transcript_packed.py` with `get_transcript_packed(args, project_path)`.
   - Exporting `get_transcript_packed` in `open_edit/agent/tools/__init__.py`.
   - Adding `"get_transcript_packed"` to `QueryProjectArgs.query` `Literal` enum in `open_edit/serve/tool_registry.py`.
   - Adding `"get_transcript_packed"` to `routing` dict in `open_edit/serve/pillar_tools.py:dispatch_query`.
   - Updating `TOOL_USAGE_GUIDE` in `open_edit/serve/tool_schemas.py`.

---

## 3. Caveats
- If `faster-whisper` is not installed or transcription fails during asset ingestion, `Asset.alignment` will be `[]`. The phrase packing formatter must handle empty alignment cleanly without raising exceptions.
- `WordAlignment` does not currently store a speaker field by default. A default `speaker="Speaker 1"` (or `speaker: Optional[str] = None` field added to `WordAlignment`) should be supported so word sequences with speaker annotations or single-speaker files are handled seamlessly.

---

## 4. Conclusion
The requirements and design for `get_transcript_packed` (Milestone 2 / R2) are fully specified and ready for implementation.
The implementation involves adding phrase packing helper functions to `open_edit/storage/transcription.py`, creating `open_edit/agent/tools/pyagent_get_transcript_packed.py`, registering the tool in `open_edit/agent/tools/__init__.py`, `tool_registry.py`, `pillar_tools.py`, and `tool_schemas.py`, and creating a comprehensive test suite in `tests/test_transcription_pack.py`.

---

## 5. Verification Method

### 5.1 Files to Inspect
- `/home/ah64/apps/mlt-pipeline/open_edit/.agents/teamwork_preview_explorer_m2_1/analysis.md`
- `open_edit/storage/transcription.py`
- `open_edit/agent/tools/pyagent_get_transcript_packed.py`
- `open_edit/agent/tools/__init__.py`
- `open_edit/serve/tool_registry.py`
- `open_edit/serve/pillar_tools.py`
- `open_edit/serve/tool_schemas.py`
- `tests/test_transcription_pack.py`

### 5.2 Verification Commands
- Run new phrase packing unit tests:
  `python3 -m pytest tests/test_transcription_pack.py`
- Run pillar tool integration tests:
  `python3 -m pytest tests/test_pillar_tools.py tests/test_tool_registry.py`
- Run full pytest regression suite:
  `python3 -m pytest tests/`

### 5.3 Invalidation Conditions
- Phrase packing formatting fails on empty alignment `[]`.
- Tool registration is omitted in `open_edit/agent/tools/__init__.py` causing `getattr(tools_mod, "get_transcript_packed")` to raise `AttributeError`.
- Existing tests fail or regress.
