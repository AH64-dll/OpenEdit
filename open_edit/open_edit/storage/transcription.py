"""faster-whisper integration for word-level alignment.

Per phase4-design-revised.md §4.2 (W1).
Optional: if faster-whisper is not installed, transcribe() returns [].
"""
from __future__ import annotations

from pathlib import Path

from open_edit.ir.types import WordAlignment

try:
    from faster_whisper import WhisperModel  # type: ignore
except ImportError:
    WhisperModel = None  # type: ignore


def _has_whisper() -> bool:
    return WhisperModel is not None


def transcribe(src: Path, model_size: str = "base") -> list[WordAlignment]:
    """Transcribe an audio/video file to word-level alignment.

    Returns [] if faster-whisper is not installed.
    """
    if not _has_whisper():
        return []
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(str(src), word_timestamps=True)
    alignments = []
    for segment in segments:
        if segment.words:
            for w in segment.words:
                alignments.append(WordAlignment(
                    word=w.word,
                    t_start=w.start,
                    t_end=w.end,
                    confidence=w.probability,
                ))
    return alignments
