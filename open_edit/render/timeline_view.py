"""timeline_view: filmstrip + waveform + word-label composite PNG for a time range.

Ported from browser-use/video-use ``helpers/timeline_view.py`` (MIT) and
adapted to OpenEdit's data model (``WordAlignment`` instead of Scribe JSON).

This is the on-demand visual layer of the transcript-first editing
mechanism: the editing agent reads the *packed transcript* for structure and
drills into a ``timeline_view`` PNG only at decision points (ambiguous
pauses, retake comparisons, cut sanity checks, and self-eval of rendered
output). It lets non-vision models delegate a single image to a vision model
instead of dumping frames.

Layout (mirrors video-use):
    header          "{name}  {start}s -> {end}s  (duration, N frames)"
    filmstrip       10 frames, 180px tall, LANCZOS, scaled to fit
    waveform        ffmpeg showwavespic (blue), silence bands shaded
    word labels     above waveform with 4px ticks
    time ruler      6 ticks with seconds
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

# ---- layout constants (from video-use) ----
FRAME_H = 180
FILMSTRIP_Y = 50
WAVE_Y = 250
WAVE_H = 220
LABEL_Y = 480
CANVAS_MIN_W = 1920
BG = (18, 18, 22)
FG = (235, 235, 235)
DIM = (110, 110, 120)
WAVE_COLOR = (140, 180, 255)
SILENCE_SHADE = (50, 80, 120, 120)
SILENCE_THRESHOLD_S = 0.4
TICK_MIN_SPACING_PX = 28
N_TICKS = 6


def _ffmpeg_available() -> bool:
    return subprocess.run(["which", "ffmpeg"], capture_output=True).returncode == 0


def extract_frames(video: Path, start: float, end: float, n_frames: int = 10) -> list[Path]:
    """Extract N evenly spaced JPEG frames from [start, end].

    Frames are written into a caller-owned temp directory (the caller is
    responsible for unlinking them; ``build_timeline_view`` does).
    """
    tmpd = Path(tempfile.mkdtemp(prefix="tlv_frames_"))
    out: list[Path] = []
    for i in range(n_frames):
        t = start + i * (end - start) / max(n_frames - 1, 1)
        p = tmpd / f"f_{i:03d}.jpg"
        subprocess.run(
            [
                "ffmpeg", "-y", "-v", "error",
                "-ss", f"{t:.3f}", "-i", str(video),
                "-frames:v", "1", "-q:v", "4",
                "-vf", "scale=320:-2",
                str(p),
            ],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        out.append(p)
    return out


def render_waveform(video: Path, start: float, end: float, width: int, height: int) -> Path:
    """Render a mono waveform PNG for [start, end] via ffmpeg showwavespic."""
    p = Path(tempfile.mktemp(suffix=".png", prefix="tlv_wave_"))
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-ss", f"{start:.3f}", "-i", str(video),
            "-t", f"{end - start:.3f}",
            "-filter_complex",
            f"aformat=channel_layouts=mono,showwavespic=s={width}x{height}:colors=#8CB4FF",
            "-frames:v", "1",
            str(p),
        ],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return p


def find_silences(
    words: list[Any], start: float, end: float, threshold_s: float = SILENCE_THRESHOLD_S
) -> list[tuple[float, float]]:
    """Find gaps >= threshold between words overlapping [start, end]."""
    gaps: list[tuple[float, float]] = []
    kept = [w for w in words if w.t_end >= start and w.t_start <= end]
    if not kept:
        return gaps
    # lead-in gap
    if kept[0].t_start - start >= threshold_s:
        gaps.append((start, kept[0].t_start))
    for prev, curr in zip(kept, kept[1:]):
        gap = curr.t_start - prev.t_end
        if gap >= threshold_s:
            gaps.append((prev.t_end, curr.t_start))
    if end - kept[-1].t_end >= threshold_s:
        gaps.append((kept[-1].t_end, end))
    return gaps


def _load_font(size: int):
    from PIL import ImageFont

    for name in ("DejaVuSansMono.ttf", "LiberationMono-Regular.ttf",
                 "Menlo.ttc", "Helvetica.ttc", "SFNSMono.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def build_timeline_view(
    video: Path,
    start: float,
    end: float,
    words: Optional[list[Any]] = None,
    n_frames: int = 10,
    width: int = CANVAS_MIN_W,
    out_path: Optional[Path] = None,
) -> Path:
    """Build the composite PNG. Returns the output path."""
    from PIL import Image, ImageDraw, ImageFont

    duration = max(end - start, 0.001)
    frames = extract_frames(video, start, end, n_frames=n_frames)
    wave_path = render_waveform(video, start, end, width=width, height=WAVE_H)

    # filmstrip
    strips = [Image.open(f).convert("RGB") for f in frames]
    max_h = max(im.height for im in strips) or 1
    strip_w = sum(im.width for im in strips) + 4 * (len(strips) - 1)
    scale = 1.0
    if strip_w > width - 100:
        scale = (width - 100) / strip_w
        strip_w = width - 100
    gap = max(2, int(4 * scale))
    canvas_h = LABEL_Y + 60
    canvas = Image.new("RGB", (width, canvas_h), BG)
    draw = ImageDraw.Draw(canvas, "RGBA")

    # header
    header_font = _load_font(22)
    draw.text((16, 12), f"{Path(video).name}   {start:.2f}s -> {end:.2f}s   ({duration:.2f}s, {n_frames} frames)",
              fill=FG, font=header_font)

    # paste scaled filmstrip
    x = 16
    for im in strips:
        h = int(im.height * scale)
        w = int(im.width * scale)
        im2 = im.resize((max(w, 1), max(h, 1)), Image.LANCZOS)
        canvas.paste(im2, (x, FILMSTRIP_Y))
        x += w + gap

    # waveform
    wave = Image.open(wave_path).convert("RGBA")
    canvas.paste(wave, (16, WAVE_Y))

    # silence shading (video-use: translucent bands under the waveform)
    if words:
        for g0, g1 in find_silences(words, start, end):
            x0 = 16 + int((g0 - start) / duration * (width - 32))
            x1 = 16 + int((g1 - start) / duration * (width - 32))
            if x1 - x0 >= 2:
                draw.rectangle([x0, WAVE_Y, x1, WAVE_Y + WAVE_H], fill=SILENCE_SHADE)

    # word labels + ticks
    label_font = _load_font(18)
    words_in = [w for w in (words or []) if w.t_end >= start and w.t_start <= end]
    last_x: float = -1e9
    for w in words_in:
        cx = 16 + (w.t_start + (w.t_end - w.t_start) / 2 - start) / duration * (width - 32)
        if cx - last_x < TICK_MIN_SPACING_PX:
            continue
        if (w.t_end - w.t_start) < 0.05:
            continue
        label = str(w.word)
        bb = draw.textbbox((0, 0), label, font=label_font)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        tx = min(max(cx - tw / 2, 16), width - 16 - tw)
        draw.line([cx, WAVE_Y + WAVE_H, cx, WAVE_Y + WAVE_H + 8], fill=WAVE_COLOR, width=2)
        draw.text((tx, LABEL_Y), label, fill=FG, font=label_font)
        last_x = cx

    # ruler
    ruler_font = _load_font(16)
    for i in range(N_TICKS):
        t = start + i * duration / (N_TICKS - 1)
        rx = 16 + int(i / (N_TICKS - 1) * (width - 32))
        draw.line([rx, LABEL_Y + 34, rx, LABEL_Y + 44], fill=DIM, width=1)
        draw.text((rx - 20, LABEL_Y + 46), f"{t:.2f}s", fill=DIM, font=ruler_font)

    silences = find_silences(words or [], start, end)
    if silences:
        draw.text((16, canvas_h - 24),
                  f"shaded bands = silences >= {int(SILENCE_THRESHOLD_S * 1000)}ms ({len(silences)} gap(s))",
                  fill=DIM, font=ruler_font)

    out = Path(out_path) if out_path else Path(tempfile.mktemp(suffix=".png", prefix="tlv_view_"))
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, optimize=True)
    for f in frames:
        f.unlink(missing_ok=True)
    wave_path.unlink(missing_ok=True)
    return out
