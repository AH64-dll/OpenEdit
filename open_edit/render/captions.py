"""One cached caption raster for preview and export; source remains editable."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from open_edit.ir.captions import CaptionCue
from open_edit.render.pipe_builder import OverlayClip


def font_path(root: Path, font_id: str | None) -> Path:
    if font_id is None:
        from open_edit.integrations.diffusion.graphics import browser_directory

        return browser_directory() / "fonts/OpenEditSans.woff2"
    if not re.fullmatch(r"[a-f0-9]{64}", font_id):
        raise ValueError("Invalid project font ID")
    path = root / ".open_edit/fonts" / f"{font_id}.font"
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != font_id:
        raise ValueError("Project font is missing or changed")
    return path


def caption_image(root: Path, cue: CaptionCue, width: int, height: int) -> Path:
    if not 16 <= width <= 7680 or not 16 <= height <= 7680:
        raise ValueError("Invalid caption canvas dimensions")
    style = cue.style
    path = font_path(root, style.font_id)
    identity = hashlib.sha256(
        json.dumps(
            {
                "schema": 1,
                "text": cue.text,
                "style": style.model_dump(),
                "size": [width, height],
                "font": hashlib.sha256(path.read_bytes()).hexdigest(),
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    cache = root / ".open_edit/cache/captions"
    cache.mkdir(parents=True, exist_ok=True)
    output = cache / f"{identity}.png"
    if output.is_file():
        return output
    scale = height / 1080
    font = ImageFont.truetype(str(path), max(1, round(style.font_size * scale)))
    stroke = round(style.stroke_width * scale)
    image = Image.new("RGBA", (width, height))
    draw = ImageDraw.Draw(image)
    padding = max(2, round(14 * scale))
    box_width = max(1, round(style.width * width) - 2 * padding)
    lines = []
    for paragraph in cue.text.split("\n"):
        line = ""
        for char in paragraph:
            if line and draw.textlength(line + char, font=font) > box_width:
                # Prefer a word boundary, while still wrapping unbroken text.
                split = line.rfind(" ")
                if split > 0:
                    lines.append(line[:split])
                    line = line[split + 1 :] + char
                else:
                    lines.append(line)
                    line = char
            else:
                line += char
        lines.append(line)
    text = "\n".join(lines)
    spacing = max(1, round(style.font_size * scale * 0.2))
    bounds = draw.multiline_textbbox((0, 0), text, font=font, spacing=spacing, stroke_width=stroke)
    text_width, text_height = bounds[2] - bounds[0], bounds[3] - bounds[1]
    left = style.x * width
    top = min(style.y * height, max(0, height - text_height - 2 * padding))
    box_right = min(width, left + style.width * width)
    draw.rounded_rectangle(
        (left, top, box_right, top + text_height + 2 * padding),
        radius=padding,
        fill=style.background,
    )
    x = (
        left + padding
        if style.align == "left"
        else box_right - text_width - padding
        if style.align == "right"
        else (left + box_right - text_width) / 2
    )
    draw.multiline_text(
        (x - bounds[0], top + padding - bounds[1]),
        text,
        font=font,
        fill=style.color,
        spacing=spacing,
        align=style.align,
        stroke_width=stroke,
        stroke_fill=style.stroke_color,
    )
    handle, pending = tempfile.mkstemp(suffix=".png", dir=cache)
    os.close(handle)
    try:
        image.save(pending)
        os.replace(pending, output)
    finally:
        Path(pending).unlink(missing_ok=True)
    return output


def caption_overlays(
    root: Path, captions: dict[str, CaptionCue], width: int, height: int
) -> list[OverlayClip]:
    return [
        OverlayClip(
            position_sec=c.start_sec,
            duration_sec=c.end_sec - c.start_sec,
            media_path=caption_image(root, c, width, height),
            label=f"caption:{id}",
            alpha=True,
            still=True,
            z_index=1000000,
        )
        for id, c in captions.items()
        if c.enabled
    ]
