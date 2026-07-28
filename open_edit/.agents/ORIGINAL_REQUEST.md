# Original User Request

## 2026-07-23T10:32:04Z

Enhance Open Edit (`/home/ah64/apps/mlt-pipeline/open_edit`) with 3 high-value features adapted from open-source video-editing agents (`video-use`): token-efficient phrase-packed transcripts, 30ms audio micro-crossfades to prevent audio pops, and waveform-assisted cut verification.

Working directory: /home/ah64/apps/mlt-pipeline/open_edit
Integrity mode: demo

## Requirements

### R1. Automatic 30ms Audio Micro-Fades in MLT Emitter
Modify `open_edit/render/emitter.py` to automatically inject 30ms audio volume fade-in and fade-out filters on clip boundaries when emitting MLT XML, eliminating audio pops/clicks at cut points.

### R2. Token-Efficient Phrase-Packed Transcript Tool (`get_transcript_packed`)
Create a new tool and module in `open_edit/storage/transcription.py` and `open_edit/agent/tools/` that formats `faster-whisper` word alignments into a silence-aware, speaker-grouped Markdown representation (`takes_packed.md`) for efficient LLM reasoning. Register the tool in `tool_schemas.py` and `open_edit/agent/tools/__init__.py`.

### R3. Waveform Cut Inspection Image Generation
Extend `open_edit/serve/visual_verify.py` to optionally generate a dual-panel waveform + video frame composite image around cut boundaries using FFmpeg `showwavespic` and `vstack`/`hstack`.

## Acceptance Criteria

### Automated Tests & Quality
- [ ] Write unit tests for 30ms audio fade insertion in `emitter.py` (`pytest tests/test_render_emitter.py`).
- [ ] Write unit tests for phrase packing in `transcription.py` (`pytest tests/test_transcription_pack.py`).
- [ ] Write unit tests for waveform composite image generation in `visual_verify.py` (`pytest tests/test_visual_verify_waveform.py`).
- [ ] All 770+ existing pytest unit tests in `open_edit` must pass cleanly without regressions (`python3 -m pytest tests/`).
