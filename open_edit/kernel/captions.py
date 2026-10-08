"""Subtitle interchange and optional transcript-to-caption source conversion."""

from __future__ import annotations

import hashlib
import io
import os
import re
import tempfile
import uuid
from pathlib import Path

from PIL import ImageFont

from open_edit.ir.captions import CaptionCue


def parse_srt(source: str) -> list[dict]:
    if len(source.encode()) > 2 * 1024 * 1024:
        raise ValueError("Subtitle file exceeds 2 MiB")
    source = source.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n").strip()
    cues = []
    pattern = r"(\d{2,}):(\d{2}):(\d{2})[,.](\d{3})"

    def seconds(parts):
        h, m, s, ms = map(int, parts)
        if m >= 60 or s >= 60:
            raise ValueError("Invalid subtitle timestamp")
        return h * 3600 + m * 60 + s + ms / 1000

    for block in re.split(r"\n\s*\n", source):
        lines = block.splitlines()
        if lines and lines[0].strip().isdigit():
            lines.pop(0)
        if not lines:
            continue
        match = re.fullmatch(pattern + r"\s*-->\s*" + pattern, lines.pop(0).strip())
        if not match:
            raise ValueError("Use SRT timestamps: HH:MM:SS,mmm --> HH:MM:SS,mmm")
        cue = CaptionCue(
            text="\n".join(lines),
            start_sec=seconds(match.groups()[:4]),
            end_sec=seconds(match.groups()[4:]),
        )
        cues.append(
            {
                "kind": "caption",
                "object_id": "caption-" + uuid.uuid4().hex,
                "data": cue.model_dump(mode="json"),
            }
        )
        if len(cues) > 1000:
            raise ValueError("Import at most 1000 captions at a time")
    return cues


def format_srt(cues: list[CaptionCue]) -> str:
    def stamp(seconds):
        value = round(seconds * 1000)
        hours, value = divmod(value, 3600000)
        minutes, value = divmod(value, 60000)
        seconds, millis = divmod(value, 1000)
        return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"

    return (
        "\n\n".join(
            f"{i}\n{stamp(c.start_sec)} --> {stamp(c.end_sec)}\n{c.text}"
            for i, c in enumerate(sorted(cues, key=lambda c: (c.start_sec, c.end_sec)), 1)
        )
        + "\n"
    )


def from_transcript(words, *, position_sec=0, in_sec=0, out_sec=float("inf")) -> list[dict]:
    phrases, phrase = [], []
    for word in words:
        if word.t_end <= in_sec or word.t_start >= out_sec:
            continue
        if phrase and (len(phrase) >= 7 or word.t_start - phrase[-1].t_end > 0.5):
            phrases.append(phrase)
            phrase = []
        phrase.append(word)
    if phrase:
        phrases.append(phrase)
    return [
        {
            "kind": "caption",
            "object_id": "caption-" + uuid.uuid4().hex,
            "data": CaptionCue(
                text=" ".join(w.word.strip() for w in phrase),
                start_sec=position_sec + max(in_sec, phrase[0].t_start) - in_sec,
                end_sec=position_sec + min(out_sec, phrase[-1].t_end) - in_sec,
            ).model_dump(mode="json"),
        }
        for phrase in phrases
    ]


def store_font(root: Path, content: bytes) -> str:
    if not 1 <= len(content) <= 8 * 1024 * 1024:
        raise ValueError("Font must be at most 8 MiB")
    try:
        ImageFont.truetype(io.BytesIO(content), 24).getmask("OpenEdit")
    except OSError as error:
        raise ValueError("Choose a valid TTF, OTF, WOFF or WOFF2 font") from error
    identity = hashlib.sha256(content).hexdigest()
    folder = root / ".open_edit/fonts"
    folder.mkdir(parents=True, exist_ok=True)
    handle, pending = tempfile.mkstemp(dir=folder)
    try:
        with os.fdopen(handle, "wb") as file:
            file.write(content)
        os.replace(pending, folder / f"{identity}.font")
    finally:
        Path(pending).unlink(missing_ok=True)
    return identity
