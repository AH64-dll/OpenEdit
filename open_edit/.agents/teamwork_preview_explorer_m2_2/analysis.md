# Milestone 2 (R2): Token-Efficient Phrase-Packed Transcript Tool Analysis

## 1. Architectural Overview & Context

Open Edit utilizes Whisper (`faster-whisper`) to extract word-level alignments (`WordAlignment`) from media assets during ingestion. While word-level alignments provide millisecond precision (`t_start`, `t_end`, `confidence`), sending raw word JSON arrays to an LLM context window causes severe token overhead (~25–30 tokens per word due to JSON key/value boilerplate and floating point numbers).

Milestone 2 introduces the **Token-Efficient Phrase-Packed Transcript Tool** (`get_transcript_packed`), which processes raw `list[WordAlignment]` sequences and packs them into readable, token-compact Markdown blocks formatted with timestamps, speaker labels, and silence markers.

---

## 2. Codebase Investigation Findings

### 2.1 Storage & IR Layer (`open_edit/storage/transcription.py` & `open_edit/ir/types.py`)
- **`open_edit/ir/types.py` (lines 79–84)**:
  `WordAlignment` currently defines:
  ```python
  class WordAlignment(BaseModel):
      word: str
      t_start: float
      t_end: float
      confidence: float = 1.0
      speaker: Optional[str] = None  # To be added/supported for speaker diarization
  ```
- **`open_edit/storage/transcription.py` (lines 1–51)**:
  Contains `transcribe(src: Path, model_size: str = "base") -> list[WordAlignment]`.
  The phrase packing logic should be added directly to `open_edit/storage/transcription.py` as `pack_transcript()` and `format_timestamp()` helper functions.

### 2.2 Agent Tools Layer (`open_edit/agent/tools/`)
- Tool implementation should be created in `open_edit/agent/tools/pyagent_get_transcript_packed.py` with signature:
  ```python
  def get_transcript_packed(args: dict, project_path: str) -> dict[str, Any]:
  ```
- Must be exported in `open_edit/agent/tools/__init__.py` and added to `__all__`.

### 2.3 Pillar Tools & Schema Registration (`open_edit/serve/`)
Open Edit uses a 4-pillar tool consolidation architecture (`query_project`, `edit_project`, `run_script`, `trigger_render`):
- **`open_edit/serve/tool_registry.py` (lines 48–60)**:
  `QueryProjectArgs` defines supported read-only queries. `get_transcript_packed` must be added to the `query` `Literal[...]` type hint.
- **`open_edit/serve/pillar_tools.py` (lines 13–35)**:
  `dispatch_query()` routes read-only requests. `get_transcript_packed` must be registered in the `routing` dictionary.
- **`open_edit/serve/tool_schemas.py` (lines 55–66)**:
  `TOOL_USAGE_GUIDE` must document `get_transcript_packed` under `query_project`.

---

## 3. Phrase Packing Algorithm Specification

### 3.1 Data Flow & Algorithm Steps

```
[ list[WordAlignment] ]
         │
         ▼
 ┌───────────────────────────────┐
 │ 1. Validate & Filter Empty     │
 └───────────────┬───────────────┘
                 │
                 ▼
 ┌───────────────────────────────┐
 │ 2. Iterate Word Alignments    │
 │    - Check Speaker Change     │
 │    - Check Silence Gap        │
 │      (gap >= pause_threshold) │
 └───────────────┬───────────────┘
                 │
      ┌──────────┴──────────┐
      ▼                     ▼
┌──────────────┐    ┌─────────────────┐
│ Speaker Tag  │    │ Silence Marker  │
│ [Speaker A]  │    │ [Silence 1.2s]  │
└──────────────┘    └─────────────────┘
      │                     │
      └──────────┬──────────┘
                 │
                 ▼
 ┌───────────────────────────────┐
 │ 3. Format Phrase Block        │
 │    [MM:SS.ms - MM:SS.ms]      │
 │    "Words combined here..."   │
 └───────────────┬───────────────┘
                 │
                 ▼
      [ Markdown String Output ]
```

### 3.2 Detailed Formatting Rules

1. **Timestamp Formatting (`[MM:SS.ms - MM:SS.ms]`)**:
   - Format: `[MM:SS.mmm - MM:SS.mmm]` where `MM` = minutes zero-padded to 2 digits, `SS` = seconds zero-padded to 2 digits, and `mmm` = milliseconds zero-padded to 3 digits.
   - Example: `t_start=1.23` and `t_end=5.45` -> `[00:01.230 - 00:05.450]`.
   - Formula:
     ```python
     def format_timestamp(seconds: float) -> str:
         mins = int(seconds // 60)
         secs = seconds % 60
         return f"{mins:02d}:{secs:06.3f}"
     ```

2. **Pause Thresholding & Silence Markers**:
   - Default `pause_threshold_sec = 0.5` seconds.
   - For consecutive words $W_{i}$ and $W_{i+1}$, calculate gap $G = W_{i+1}.\text{t\_start} - W_{i}.\text{t\_end}$.
   - If $G \ge \text{pause\_threshold\_sec}$:
     - Close the current phrase block (its end timestamp is $W_{i}.\text{t\_end}$).
     - Emit a silence marker line: `[Silence G.Gs]` (e.g. `[Silence 1.2s]`).
     - Start a new phrase block with $W_{i+1}.\text{t\_start}$.

3. **Speaker Transitions**:
   - If `W_{i+1}.speaker != W_{i}.speaker` and speaker labels are present:
     - Close the current phrase block.
     - Emit a speaker header: `[Speaker X]`.
     - Start a new phrase block.

4. **Token-Efficiency Impact**:
   - Raw JSON representation of 100 words: ~2,500 tokens.
   - Phrase-packed Markdown representation of 100 words (grouped into ~10 phrases): ~350 tokens (~86% reduction in context window usage).

---

## 4. Proposed Implementation Specifications & Code Snippets

### 4.1 Addition to `open_edit/storage/transcription.py`

```python
def format_timestamp(seconds: float) -> str:
    """Format seconds into MM:SS.ms string format (e.g. 01:23.450)."""
    mins = int(seconds // 60)
    secs = seconds % 60
    return f"{mins:02d}:{secs:06.3f}"


def pack_transcript(
    alignment: list[WordAlignment],
    pause_threshold_sec: float = 0.5,
) -> str:
    """Pack word-level alignments into token-efficient phrase blocks.
    
    Returns a Markdown string formatted with phrase range timestamps,
    speaker labels (if available), and silence markers.
    """
    if not alignment:
        return ""

    lines: list[str] = []
    current_words: list[str] = []
    phrase_start: float = alignment[0].t_start
    prev_end: float = alignment[0].t_start
    current_speaker: str | None = None

    for i, w in enumerate(alignment):
        gap = w.t_start - prev_end if i > 0 else 0.0
        speaker_changed = (w.speaker is not None) and (w.speaker != current_speaker)

        if i > 0 and (gap >= pause_threshold_sec or speaker_changed):
            # Flush existing phrase block
            if current_words:
                ts_str = f"[{format_timestamp(phrase_start)} - {format_timestamp(prev_end)}]"
                lines.append(f"{ts_str} {' '.join(current_words)}")
                current_words = []

            # Insert silence marker if gap threshold exceeded
            if gap >= pause_threshold_sec:
                lines.append(f"[Silence {gap:.1f}s]")

            # Insert speaker header if speaker changed
            if speaker_changed:
                current_speaker = w.speaker
                lines.append(f"[{w.speaker}]")

            phrase_start = w.t_start
        elif i == 0 and w.speaker is not None:
            current_speaker = w.speaker
            lines.append(f"[{w.speaker}]")

        current_words.append(w.word.strip())
        prev_end = w.t_end

    # Flush final phrase block
    if current_words:
        ts_str = f"[{format_timestamp(phrase_start)} - {format_timestamp(prev_end)}]"
        lines.append(f"{ts_str} {' '.join(current_words)}")

    return "\n".join(lines)
```

### 4.2 New File `open_edit/agent/tools/pyagent_get_transcript_packed.py`

```python
"""pyagent_get_transcript_packed: returns token-efficient phrase-packed transcript."""
from __future__ import annotations

from typing import Any
from open_edit.agent.tools._helpers import get_asset_store
from open_edit.storage.transcription import pack_transcript


def get_transcript_packed(args: dict, project_path: str) -> dict[str, Any]:
    """Return phrase-packed transcript for `args['asset_hash']`.
    
    Args:
        args: {
            "asset_hash": str,
            "pause_threshold_sec": float (optional, default 0.5)
        }
        project_path: path to project directory.
        
    Returns:
        {"status": "ok", "transcript": str, "phrase_count": int}
        or {"status": "error", "error": str}
    """
    try:
        asset_hash = args.get("asset_hash")
        if not asset_hash:
            return {"status": "error", "error": "asset_hash parameter is required"}

        store = get_asset_store(project_path)
        asset = store.get(asset_hash)
        if asset is None:
            return {"status": "error", "error": f"asset {asset_hash} not found"}

        if not asset.alignment:
            return {"status": "error", "error": "asset has no word-level alignment"}

        pause_thresh = float(args.get("pause_threshold_sec", 0.5))
        transcript_md = pack_transcript(asset.alignment, pause_threshold_sec=pause_thresh)
        
        return {
            "status": "ok",
            "transcript": transcript_md,
            "phrase_count": len([line for line in transcript_md.splitlines() if line.startswith("[")]),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
```

---

## 5. Unit Test Strategy (`tests/test_transcription_pack.py`)

A new test file `tests/test_transcription_pack.py` will be created using `pytest` and `unittest.TestCase` patterns matching existing storage tests in `tests/test_storage/`.

### Test Case Matrix

| Test Method Name | Target Scenario | Input Description | Expected Result |
|------------------|-----------------|-------------------|-----------------|
| `test_pack_empty_alignment` | Edge Case | `alignment = []` | Returns `""` |
| `test_pack_single_continuous_phrase` | Basic Grouping | 3 words without gaps (<0.5s gap) | 1 phrase line: `[00:00.000 - 00:01.500] Hello world test` |
| `test_pack_silence_gaps` | Silence Markers | 2 words, 1.2s gap, 2 words | Phrase 1, `[Silence 1.2s]`, Phrase 2 |
| `test_pack_speaker_changes` | Diarization | Speaker 1 (2 words), Speaker 2 (2 words) | `[Speaker 1]`, Phrase 1, `[Speaker 2]`, Phrase 2 |
| `test_custom_pause_threshold` | Parameterization | Gap of 0.4s with `pause_threshold_sec=0.3` vs `0.5` | Threshold 0.3 splits into 2 phrases; threshold 0.5 groups into 1 |
| `test_format_timestamp_edge_cases` | Formatting | `0.0s`, `65.123s`, `3605.001s` | `00:00.000`, `01:05.123`, `60:05.001` |
| `test_tool_get_transcript_packed_success` | Tool Integration | Valid asset with alignment in `AssetStore` | `status: "ok"`, non-empty `transcript` string |
| `test_tool_get_transcript_packed_missing_asset` | Tool Error | Non-existent `asset_hash` | `status: "error"`, message contains asset hash |
| `test_pillar_query_dispatch` | Pillar API | `dispatch_query("get_transcript_packed", ...)` | Calls underlying tool and returns valid result |

---

## 6. Layout Compliance

- Source files:
  - `open_edit/storage/transcription.py` (implementation)
  - `open_edit/agent/tools/pyagent_get_transcript_packed.py` (tool handler)
  - `open_edit/agent/tools/__init__.py` (tool export)
  - `open_edit/serve/tool_registry.py` & `pillar_tools.py` (pillar integration)
- Test files:
  - `tests/test_transcription_pack.py`
- Agent metadata:
  - `.agents/teamwork_preview_explorer_m2_2/` contains ONLY markdown reports and briefing metadata. No source code or tests will be created in `.agents/`.
