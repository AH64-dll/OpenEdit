# Project: Open Edit Features Implementation

## Architecture
Open Edit is a video editing and rendering pipeline powered by MLT framework, Whisper transcription, FFmpeg, and AI editing tools.
- `open_edit/render/emitter.py`: Generates MLT XML from timeline clip configurations.
- `open_edit/storage/transcription.py` & `open_edit/agent/tools/`: Audio transcription parsing, phrase packing for LLM context optimization, and agent tool registration.
- `open_edit/serve/visual_verify.py`: Cut boundary frame extraction and visual/waveform inspection tools.

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | R1: 30ms Audio Micro-Fades | `open_edit/render/emitter.py`, `tests/test_render_emitter.py` | None | DONE |
| 2 | R2: Phrase-Packed Transcript Tool | `open_edit/storage/transcription.py`, `open_edit/agent/tools/`, `tests/test_transcription_pack.py` | None | DONE |
| 3 | R3: Waveform Cut Inspection Image | `open_edit/serve/visual_verify.py`, `tests/test_visual_verify_waveform.py` | None | DONE |
| 4 | M4: Full Test Suite Verification | `pytest tests/` | M1, M2, M3 | DONE |


## Interface Contracts
### Emitter ↔ MLT Engine
- Automatic 30ms micro-fade filter tags injected into XML clip elements (`fadeIn` / `fadeOut` or volume filters with duration 30ms / 0.03s or frames equivalent at project FPS).

### Transcription ↔ Agent Tools
- `get_transcript_packed`: Returns Markdown string formatted as phrase-packed transcript with silence gaps and speaker tags. Registered in `tool_schemas.py` and `open_edit/agent/tools/__init__.py`.

### Visual Verify ↔ FFmpeg
- `generate_waveform_inspection_image`: Takes cut timestamp / clip info, runs FFmpeg `showwavespic` and stacks waveform with video frame output.

## Code Layout
- `open_edit/render/emitter.py`
- `open_edit/storage/transcription.py`
- `open_edit/agent/tools/`
- `open_edit/serve/visual_verify.py`
- `tests/`
