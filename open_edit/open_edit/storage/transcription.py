"""faster-whisper integration for word-level alignment.

Per phase4-design-revised.md §4.2 (W1).
Optional: if faster-whisper is not installed, transcribe() returns [].

Environment (optional):
  OPEN_EDIT_WHISPER_MODEL   — model size (default: ``base``; use ``small`` for Arabic)
  OPEN_EDIT_WHISPER_LANGUAGE — e.g. ``ar``, ``en``; unset = auto-detect
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from open_edit.ir.types import WordAlignment

try:
    from faster_whisper import WhisperModel  # type: ignore
except ImportError:
    WhisperModel = None  # type: ignore


_log = logging.getLogger(__name__)


def _has_whisper() -> bool:
    return WhisperModel is not None


def whisper_model_size(explicit: str | None = None) -> str:
    """Resolve Whisper model size from arg or ``OPEN_EDIT_WHISPER_MODEL``."""
    if explicit:
        return explicit
    return (os.environ.get("OPEN_EDIT_WHISPER_MODEL") or "base").strip() or "base"


def whisper_language(explicit: str | None = None) -> str | None:
    """Resolve language override from arg or ``OPEN_EDIT_WHISPER_LANGUAGE``.

    Empty / unset means auto-detect.
    """
    if explicit is not None:
        value = explicit.strip()
        return value or None
    raw = (os.environ.get("OPEN_EDIT_WHISPER_LANGUAGE") or "").strip()
    return raw or None


def transcribe(
    src: Path,
    model_size: str | None = None,
    *,
    language: str | None = None,
) -> list[WordAlignment]:
    """Transcribe an audio/video file to word-level alignment.

    ``model_size`` defaults to ``OPEN_EDIT_WHISPER_MODEL`` or ``base``.
    ``language`` defaults to ``OPEN_EDIT_WHISPER_LANGUAGE`` or auto-detect.

    Returns [] if faster-whisper is not installed, or if transcription
    raises for any reason (one bad file should not break the whole batch).
    """
    if not _has_whisper():
        return []
    size = whisper_model_size(model_size)
    lang = whisper_language(language)
    try:
        model = WhisperModel(size, device="cpu", compute_type="int8")
        kwargs: dict = {"word_timestamps": True}
        if lang:
            kwargs["language"] = lang
        segments, info = model.transcribe(str(src), **kwargs)
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
    except Exception as exc:
        _log.warning("transcribe() failed for %s: %s", src, exc)
        return []


def format_timestamp(seconds: float) -> str:
    """Format seconds into timestamp string MM:SS.ms (or HH:MM:SS.ms if >= 1hr)."""
    sec_val = max(0.0, float(seconds or 0.0))
    if sec_val >= 3600:
        hours = int(sec_val // 3600)
        rem = sec_val % 3600
        minutes = int(rem // 60)
        secs = rem % 60
        return f"{hours:02d}:{minutes:02d}:{secs:05.2f}"
    else:
        minutes = int(sec_val // 60)
        secs = sec_val % 60
        return f"{minutes:02d}:{secs:05.2f}"


def pack_transcript(
    alignment: list[WordAlignment],
    pause_threshold_sec: float = 0.5,
) -> str:
    """Format word alignments into silence-aware, speaker-grouped Markdown string.

    Phrase-packs word alignments based on inter-word silence gaps (>= pause_threshold_sec)
    and speaker transitions.
    """
    if not alignment:
        return ""

    lines: list[str] = []
    current_phrase: list[WordAlignment] = []

    def flush_phrase(phrase: list[WordAlignment]) -> None:
        if not phrase:
            return
        t_start = phrase[0].t_start
        t_end = phrase[-1].t_end
        speaker = phrase[0].speaker
        words_str = " ".join(w.word.strip() for w in phrase if w.word.strip())

        start_fmt = format_timestamp(t_start)
        end_fmt = format_timestamp(t_end)
        ts_hdr = f"[{start_fmt} - {end_fmt}]"

        if speaker:
            line = f"{ts_hdr} [{speaker}] {words_str}"
        else:
            line = f"{ts_hdr} {words_str}"
        lines.append(line)

    for word_obj in alignment:
        if not current_phrase:
            current_phrase.append(word_obj)
            continue

        prev_word = current_phrase[-1]
        gap = word_obj.t_start - prev_word.t_end
        speaker_changed = (word_obj.speaker != current_phrase[0].speaker)

        if gap >= pause_threshold_sec:
            flush_phrase(current_phrase)
            current_phrase = []
            lines.append(f"*--- Silence ({gap:.2f}s) ---*")
            current_phrase.append(word_obj)
        elif speaker_changed:
            flush_phrase(current_phrase)
            current_phrase = []
            current_phrase.append(word_obj)
        else:
            current_phrase.append(word_obj)

    if current_phrase:
        flush_phrase(current_phrase)

    return "\n".join(lines)
