"""Image upload helpers + temp-file cleanup for pasted/dropped images.

The chat UI accepts base64 image data URLs, decodes them, validates the
extension and size, and writes them to `/tmp/pyagent_uploads/`. A background
task purges uploads older than `max_age_hours`.
"""
from __future__ import annotations

import asyncio
import base64
import re
import time
import uuid
from pathlib import Path

ALLOWED_IMAGE_EXTS = {"png", "jpg", "jpeg", "gif", "webp"}
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB

UPLOAD_DIR = Path("/tmp/pyagent_uploads")


def save_base64_image(data_url: str) -> str:
    """Decode a base64 image data URL, validate, and write to /tmp/pyagent_uploads.

    Returns the path to the saved file. Raises ValueError for invalid input.
    """
    if data_url.startswith("data:image/"):
        match = re.match(r"^data:image/(\w+);base64,(.+)$", data_url)
        if match:
            ext = match.group(1).lower()
            base64_data = match.group(2)
        else:
            ext = "png"
            base64_data = data_url
    else:
        ext = "png"
        base64_data = data_url

    if ext not in ALLOWED_IMAGE_EXTS:
        raise ValueError(f"Unsupported image format: {ext}")

    try:
        img_data = base64.b64decode(base64_data)
    except Exception as e:
        raise ValueError(f"Invalid base64 encoding: {e}")

    if len(img_data) > MAX_IMAGE_SIZE:
        raise ValueError(f"Image too large: {len(img_data)} bytes (max {MAX_IMAGE_SIZE})")

    if UPLOAD_DIR.is_symlink():
        raise OSError("Upload directory cannot be a symbolic link")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    file_path = UPLOAD_DIR / f"{uuid.uuid4()}.{ext}"
    file_path.write_bytes(img_data)
    return str(file_path)


def cleanup_stale_uploads(max_age_hours: int = 1) -> None:
    """Delete uploads older than `max_age_hours` from the upload dir."""
    if not UPLOAD_DIR.exists():
        return
    cutoff = time.time() - max_age_hours * 3600
    for f in UPLOAD_DIR.iterdir():
        if f.is_file() and f.stat().st_mtime < cutoff:
            try:
                f.unlink(missing_ok=True)
            except Exception:
                pass


async def periodic_cleanup(interval_sec: int = 1800) -> None:
    """Background task: run `cleanup_stale_uploads` every `interval_sec`."""
    while True:
        await asyncio.sleep(interval_sec)
        cleanup_stale_uploads()
