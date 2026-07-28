# Execution Plan: Open Edit 3 Features Implementation

## Overview
Implement 3 high-value features for Open Edit and verify all unit tests pass without regressions.

## Milestones

### Milestone 1: R1. Automatic 30ms Audio Micro-Fades in MLT Emitter
- **Target Files**: `open_edit/render/emitter.py`, `tests/test_render_emitter.py`
- **Objective**: Automatically inject 30ms audio volume fade-in and fade-out filters on clip boundaries when emitting MLT XML to eliminate audio pops/clicks at cut points.
- **Workflow**:
  1. Explorer investigation on `emitter.py` and existing MLT XML emission structure.
  2. Worker implementation of 30ms audio micro-fades and unit tests.
  3. Reviewer code review & verification.
  4. Challenger stress-test and verification.
  5. Forensic Auditor integrity check.

### Milestone 2: R2. Token-Efficient Phrase-Packed Transcript Tool (`get_transcript_packed`)
- **Target Files**: `open_edit/storage/transcription.py`, `open_edit/agent/tools/get_transcript_packed.py` (or as appropriate), `open_edit/agent/tools/tool_schemas.py`, `open_edit/agent/tools/__init__.py`, `tests/test_transcription_pack.py`
- **Objective**: Format `faster-whisper` word alignments into a silence-aware, speaker-grouped Markdown representation (`takes_packed.md`) for efficient LLM reasoning. Register tool in tool schemas and exports.
- **Workflow**:
  1. Explorer investigation on transcription structure and tool definitions.
  2. Worker implementation of phrase packing, tool registration, and unit tests.
  3. Reviewer code review & verification.
  4. Challenger stress-test and verification.
  5. Forensic Auditor integrity check.

### Milestone 3: R3. Waveform Cut Inspection Image Generation
- **Target Files**: `open_edit/serve/visual_verify.py`, `tests/test_visual_verify_waveform.py`
- **Objective**: Extend `visual_verify.py` to optionally generate a dual-panel waveform + video frame composite image around cut boundaries using FFmpeg `showwavespic` and `vstack`/`hstack`.
- **Workflow**:
  1. Explorer investigation on `visual_verify.py` and FFmpeg filters.
  2. Worker implementation of waveform composite image generation and unit tests.
  3. Reviewer code review & verification.
  4. Challenger stress-test and verification.
  5. Forensic Auditor integrity check.

### Milestone 4: Full Suite Regression Verification & Final Sign-off
- **Objective**: Run full pytest test suite (`pytest tests/`) ensuring 770+ tests pass cleanly.
- **Workflow**: Reviewer / Challenger verification across all test suites, Forensic Auditor audit, final handoff to parent.
