# Analysis Report: Token-Efficient Phrase-Packed Transcript Tool (Milestone 2 / R2)

## 1. Executive Summary
This analysis details the design, data format specifications, tool registration workflow, and step-by-step implementation strategy for Milestone 2 (R2: Token-Efficient Phrase-Packed Transcript Tool `get_transcript_packed`). 

The objective is to format `faster-whisper` word alignments (stored in `Asset.alignment` sidecars) into a silence-aware, speaker-grouped Markdown representation (`takes_packed.md`) optimized for LLM reasoning token budget.

---

## 2. Existing Data Structures & Architecture Analysis

### 2.1 Storage & Transcription Models
- **`open_edit/storage/transcription.py`**:
  - `transcribe(src: Path, model_size: str = "base") -> list[WordAlignment]` uses `faster-whisper.WhisperModel` (if installed) to derive word-level alignments.
  - Returns a list of `WordAlignment` objects.
- **`open_edit/ir/types.py`**:
  - `WordAlignment`:
    ```python
    class WordAlignment(BaseModel):
        word: str
        t_start: float
        t_end: float
        confidence: float = 1.0
        speaker: Optional[str] = None  # Optional speaker label
    ```
  - `Asset`:
    ```python
    class Asset(BaseModel):
        asset_hash: str
        original_path: str
        stored_path: str
        type: Literal["video", "audio", "image"]
        duration_sec: float = 0.0
        has_audio: bool = False
        alignment: list[WordAlignment] = Field(default_factory=list)
    ```
- **`open_edit/storage/assets.py`**:
  - Assets are stored in CAS (`<assets_dir>/<hash[:2]>/<hash>`) with sidecar JSON files (`<hash>.meta.json`).
  - During `ingest_paths()`, audio media is transcribed via `transcribe()`, and `alignment` is serialized into `<hash>.meta.json`.

---

## 3. Data Format Specification for `takes_packed.md`

### 3.1 Phrase Packing Algorithm
Raw word alignments contain individual timestamps for every word, consuming thousands of LLM context tokens.
Phrase packing condenses word sequences into phrase blocks based on two criteria:
1. **Silence Gaps**: Inter-word silence `gap = curr.t_start - prev.t_end`. When `gap >= pause_threshold_s` (default `0.5s`):
   - End the current phrase block.
   - Insert a silence marker line: `*--- Silence (<gap:.2f>s) ---*`.
   - Start a new phrase block on the next line.
2. **Speaker Changes**: When `curr.speaker != prev.speaker` (or speaker tag changes):
   - End the current phrase block.
   - Start a new phrase block with the new speaker tag.

### 3.2 Timestamp Formatting
- Format: `[MM:SS.ss - MM:SS.ss]` (or `[HH:MM:SS.ss - HH:MM:SS.ss]` for duration >= 1 hr).
- Example: `t_start = 1.25`, `t_end = 4.80` -> `[00:01.25 - 00:04.80]`.

### 3.3 Output Markdown Format
```markdown
# Transcript: {asset_hash}
- Total Duration: {duration_s:.2f}s
- Words: {word_count}
- Silence Threshold: {pause_threshold_s}s

## Packed Phrases

[00:00.00 - 00:02.50] [Speaker 1] Hello world welcome to open edit.
*--- Silence (1.20s) ---*
[00:03.70 - 00:05.10] [Speaker 2] Thanks for having me today.
```

### 3.4 Edge Case Handling
- **Empty Alignment (`[]`)**:
  Returns:
  ```markdown
  # Transcript: {asset_hash}
  (No transcript alignment available)
  ```
- **No Speaker Specified**: Defaults to `[Speaker 1]` (or `[SPEAKER_00]`).
- **Consecutive Punctuation / Spacing**: Cleanly strip and join words with single spaces.

---

## 4. Tool Definition & Registration Architecture

To make `get_transcript_packed` seamlessly callable by both direct agent tool execution and the 4-pillar tool system (`query_project`), the following registration workflow must be followed:

1. **Tool Core Function (`open_edit/agent/tools/pyagent_get_transcript_packed.py`)**:
   - Signature: `get_transcript_packed(args: dict, project_path: str) -> dict`.
   - Accepts `args`: `{"asset_hash": str, "pause_threshold_s": float (optional, default 0.5), "write_file": bool (optional, default False)}`.
   - Loads asset via `get_asset_store(project_path).get(asset_hash)`.
   - Formats transcript using `pack_transcript()` from `transcription.py`.
   - Optionally writes output to `<project>/.open_edit/takes_packed.md` if `write_file=True`.
   - Returns:
     ```python
     {
         "status": "ok",
         "asset_hash": asset_hash,
         "transcript_md": markdown_str,
         "phrase_count": phrase_count,
         "total_words": total_words,
         "total_silence_s": total_silence_s,
         "file_path": str(file_path) if write_file else None,
     }
     ```

2. **Package Export (`open_edit/agent/tools/__init__.py`)**:
   - Import `get_transcript_packed` from `open_edit.agent.tools.pyagent_get_transcript_packed`.
   - Add `"get_transcript_packed"` to `__all__`.
   - Allows `getattr(open_edit.agent.tools, "get_transcript_packed")` dispatch by `tool_executor.py` / `pi_bridge.py`.

3. **Pillar Tool Registration (`open_edit/serve/tool_registry.py`)**:
   - Add `"get_transcript_packed"` to `QueryProjectArgs.query` `Literal` enum:
     ```python
     query: Literal[
         "list_assets",
         "get_pending_notes",
         "get_style_profile",
         "analyze_narrative",
         "search_assets",
         "get_transcript_packed",
     ]
     ```

4. **Query Routing (`open_edit/serve/pillar_tools.py`)**:
   - In `dispatch_query`:
     ```python
     from open_edit.agent.tools import get_transcript_packed
     routing["get_transcript_packed"] = get_transcript_packed
     ```

5. **Schema Guide Update (`open_edit/serve/tool_schemas.py`)**:
   - Add `- "get_transcript_packed" → get silence-aware, speaker-grouped phrase transcript` to `TOOL_USAGE_GUIDE`.

---

## 5. Implementation Strategy & Verification Plan

### 5.1 Step-by-Step Task Breakdown
1. **Extend `open_edit/storage/transcription.py`**:
   - Implement `format_timestamp(seconds: float) -> str`.
   - Implement `pack_transcript(alignment: list[WordAlignment], pause_threshold_s: float = 0.5, default_speaker: str = "Speaker 1", title: str = "Transcript") -> tuple[str, dict]`.
2. **Create `open_edit/agent/tools/pyagent_get_transcript_packed.py`**:
   - Implement `get_transcript_packed(args: dict, project_path: str) -> dict`.
3. **Update Registration Files**:
   - Update `open_edit/agent/tools/__init__.py`.
   - Update `open_edit/serve/tool_registry.py`.
   - Update `open_edit/serve/pillar_tools.py`.
   - Update `open_edit/serve/tool_schemas.py`.
4. **Create Test Suite (`tests/test_transcription_pack.py`)**:
   - Unit tests for timestamp formatting.
   - Unit tests for phrase packing (silence gaps, speaker transitions, empty alignments).
   - Unit tests for tool invocation via `get_transcript_packed()` and `dispatch_query()`.

### 5.2 Verification Commands
- `python3 -m pytest tests/test_transcription_pack.py`
- `python3 -m pytest tests/test_pillar_tools.py tests/test_tool_registry.py`
- `python3 -m pytest tests/`
