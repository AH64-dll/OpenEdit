# Milestone 2 (R2): Token-Efficient Phrase-Packed Transcript Tool Handoff Report

## 1. Observation

- **Project Metadata & Requirements**:
  - `PROJECT.md` line 13 defines Milestone 2 scope: `open_edit/storage/transcription.py`, `open_edit/agent/tools/`, `tests/test_transcription_pack.py`.
  - `PROJECT.md` line 22 states: "`get_transcript_packed`: Returns Markdown string formatted as phrase-packed transcript with silence gaps and speaker tags. Registered in `tool_schemas.py` and `open_edit/agent/tools/__init__.py`."

- **Existing Code Base Structure**:
  - `open_edit/storage/transcription.py` (lines 1–51) currently exports `transcribe(src: Path, model_size: str = "base") -> list[WordAlignment]`.
  - `open_edit/ir/types.py` (lines 79–84) defines `WordAlignment` model:
    ```python
    class WordAlignment(BaseModel):
        word: str
        t_start: float
        t_end: float
        confidence: float = 1.0
    ```
  - `open_edit/agent/tools/` currently contains 15 tool modules (e.g. `pyagent_propose_silence_cuts.py`, `pyagent_list_assets.py`, `_helpers.py`).
  - `open_edit/agent/tools/__init__.py` (lines 21–52) exports all tool functions in `__all__`.
  - `open_edit/serve/tool_registry.py` (lines 48–60) defines `QueryProjectArgs` with `query: Literal["list_assets", "get_pending_notes", "get_style_profile", "analyze_narrative", "search_assets"]`.
  - `open_edit/serve/pillar_tools.py` (lines 13–35) defines `dispatch_query` routing map for read-only queries.

- **Existing Unit Tests**:
  - `tests/test_storage/test_transcription.py` tests Whisper model wrapping using `unittest.TestCase` and `unittest.mock.patch`.
  - `tests/test_storage/test_assets_alignment.py` tests `WordAlignment` Pydantic serialization and `AssetStore` ingestion.

---

## 2. Logic Chain

1. **Observation**: Raw `WordAlignment` lists have high per-word token overhead (~25-30 tokens/word in JSON).
   **Step 1**: To optimize context budget for LLM agents, consecutive word alignments must be packed into phrase blocks with range timestamps (`[MM:SS.ms - MM:SS.ms]`) and optional speaker tags (`[Speaker X]`).

2. **Observation**: Silence gap detection logic in `open_edit/agent/skills/silence_cutter.py` uses threshold check `curr.t_start - prev.t_end >= threshold`.
   **Step 2**: The phrase packing function `pack_transcript(alignment, pause_threshold_sec=0.5)` should iterate word alignments, trigger phrase boundaries on pause thresholds ($\ge 0.5\text{s}$) or speaker changes, and emit `[Silence X.Xs]` markers for gaps.

3. **Observation**: The tool architecture routes requests via `query_project` (Pillar tool 1) to functions exposed in `open_edit.agent.tools`.
   **Step 3**: A new tool wrapper `pyagent_get_transcript_packed.py` must be added to `open_edit/agent/tools/`, re-exported in `__init__.py`, and registered in `QueryProjectArgs` (`tool_registry.py`) and `dispatch_query` (`pillar_tools.py`).

4. **Observation**: Existing test patterns in `tests/test_storage/` use `unittest.TestCase` combined with `pytest` compatibility.
   **Step 4**: `tests/test_transcription_pack.py` should follow the same pattern, covering empty alignments, single phrase, silence gaps, speaker changes, parameterization, and pillar integration.

---

## 3. Caveats

- **Speaker Diarization Availability**: `WordAlignment` currently does not explicitly declare a `speaker` field. Adding `speaker: Optional[str] = None` to `WordAlignment` in `open_edit/ir/types.py` is recommended for full forward-compatibility with diarization tools.
- **Whisper Integration Dependency**: `get_transcript_packed` assumes word alignment data is present on the `Asset` (populated during asset ingestion via `transcribe()`). If an asset lacks audio or transcription failed, the tool returns an explicit error dict `{"status": "error", "error": "..."}`.

---

## 4. Conclusion

The specification, algorithm design, tool integration plan, and test strategy for Milestone 2 (R2: Token-Efficient Phrase-Packed Transcript Tool) are fully defined and ready for implementation.

### Implementation Checklist for Implementer:
1. Update `WordAlignment` model in `open_edit/ir/types.py` (add `speaker: Optional[str] = None`).
2. Add `pack_transcript` and `format_timestamp` to `open_edit/storage/transcription.py`.
3. Create `open_edit/agent/tools/pyagent_get_transcript_packed.py`.
4. Re-export `get_transcript_packed` in `open_edit/agent/tools/__init__.py`.
5. Update `QueryProjectArgs` in `open_edit/serve/tool_registry.py` and `dispatch_query` in `open_edit/serve/pillar_tools.py`.
6. Document in `open_edit/serve/tool_schemas.py` (`TOOL_USAGE_GUIDE`).
7. Implement test suite `tests/test_transcription_pack.py`.

---

## 5. Verification Method

To verify the implementation once completed by the implementer:

1. **Run Unit Tests**:
   ```bash
   pytest tests/test_transcription_pack.py -v
   ```
2. **Run Full Test Suite**:
   ```bash
   pytest tests/
   ```
3. **Verify Tool Registration**:
   Inspect `open_edit/serve/tool_registry.py`, `open_edit/serve/pillar_tools.py`, and `open_edit/agent/tools/__init__.py` to ensure `get_transcript_packed` is properly exported and routed.
4. **Layout Verification**:
   Ensure `.agents/` contains only metadata files (`ORIGINAL_REQUEST.md`, `BRIEFING.md`, `progress.md`, `analysis.md`, `handoff.md`).
