# Changes Summary - Milestone 2 (Token-Efficient Phrase-Packed Transcript Tool)

## Modified & Created Files

1. **`open_edit/ir/types.py`**
   - Added `speaker: Optional[str] = None` optional field to `WordAlignment` model.

2. **`open_edit/storage/transcription.py`**
   - Added `format_timestamp(seconds: float) -> str` to format time in `MM:SS.ms` (or `HH:MM:SS.ms` if >= 1 hour).
   - Added `pack_transcript(alignment: list[WordAlignment], pause_threshold_sec: float = 0.5) -> str` to group word alignments into silence-aware (`*--- Silence (<gap:.2f>s) ---*`) and speaker-grouped (`[Speaker X]`) Markdown phrases. Gracefully handles empty alignments (`[]`).

3. **`open_edit/agent/tools/pyagent_get_transcript_packed.py`** (New File)
   - Implemented `get_transcript_packed(args: dict, project_path: str | Path) -> dict` tool handler. Fetches asset from CAS store and formats phrase-packed transcript markdown.

4. **`open_edit/agent/tools/__init__.py`**
   - Exported `get_transcript_packed` and added it to `__all__`.

5. **`open_edit/serve/tool_registry.py`**
   - Added `"get_transcript_packed"` to `QueryProjectArgs.query` `Literal` enum.

6. **`open_edit/serve/pillar_tools.py`**
   - Imported `get_transcript_packed` and added `"get_transcript_packed"` to `dispatch_query` routing dictionary.

7. **`open_edit/serve/tool_schemas.py`**
   - Added `"get_transcript_packed"` documentation entry to `TOOL_USAGE_GUIDE`.

8. **`tests/test_transcription_pack.py`** (New File)
   - Created comprehensive unit test suite covering `format_timestamp`, `pack_transcript` (empty alignments, speaker changes, silence gaps, unlabeled speakers), `get_transcript_packed` tool handler, schema validation, and `dispatch_query` routing.

## Test Output

```
$ pytest tests/test_transcription_pack.py tests/test_pillar_tools.py tests/test_tool_registry.py
============================= test session starts ==============================
platform linux -- Python 3.14.0a3, pytest-8.3.4, pluggy-1.5.0
rootdir: /home/ah64/apps/mlt-pipeline/open_edit
collected 21 items

tests/test_transcription_pack.py ........                               [ 38%]
tests/test_pillar_tools.py .......                                      [ 71%]
tests/test_tool_registry.py ......                                      [100%]

============================== 21 passed in 0.26s ==============================
```
