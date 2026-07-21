"""Content-addressed asset store with ffprobe metadata.

Layout: <assets_dir>/<sha256[:2]>/<sha256>
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from open_edit.ir.types import Asset
from open_edit.storage.transcription import transcribe


CHUNK_SIZE = 65536


def _hash_file(path: Path) -> str:
    """Compute SHA-256 of a file as a hex string."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK_SIZE), b""):
            h.update(chunk)
    return h.hexdigest()


def _probe_media(path: str) -> dict:
    """Run ffprobe on a media file and return parsed metadata."""
    src = Path(path)
    if not src.exists():
        raise FileNotFoundError(path)

    fmt_result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_format", "-show_streams",
            "-of", "json", str(src),
        ],
        capture_output=True, text=True, check=True,
    )
    info = json.loads(fmt_result.stdout)
    fmt = info.get("format", {})
    streams = info.get("streams", [])

    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

    fps = None
    if video_stream and "r_frame_rate" in video_stream:
        num, _, denom = video_stream["r_frame_rate"].partition("/")
        if denom and denom != "0":
            fps = float(num) / float(denom)
        elif num:
            fps = float(num)

    duration_sec = float(fmt.get("duration", 0.0))
    width = int(video_stream["width"]) if video_stream and "width" in video_stream else None
    height = int(video_stream["height"]) if video_stream and "height" in video_stream else None
    codec = video_stream.get("codec_name") if video_stream else None

    if audio_stream and not video_stream:
        media_type = "audio"
    elif video_stream:
        media_type = "video"
    elif audio_stream:
        media_type = "audio"
    else:
        media_type = "video"

    return {
        "duration_sec": duration_sec,
        "fps": fps,
        "width": width,
        "height": height,
        "codec": codec,
        "has_audio": audio_stream is not None,
        "type": media_type,
    }


class AssetStore:
    """Content-addressed media asset store."""

    def __init__(self, assets_dir: str | Path):
        self.assets_dir = Path(assets_dir)
        self.assets_dir.mkdir(parents=True, exist_ok=True)

    def _cas_path(self, asset_hash: str) -> Path:
        return self.assets_dir / asset_hash[:2] / asset_hash

    def _sidecar_path(self, asset_hash: str) -> Path:
        """Path to the metadata sidecar JSON next to the CAS file."""
        return self.assets_dir / asset_hash[:2] / f"{asset_hash}.meta.json"

    def ingest(self, source_path: str) -> Asset:
        return self.ingest_paths([source_path])[0]

    def ingest_paths(
        self, paths: list[str],
        license: str = "",
        attribution: str = "",
    ) -> list[Asset]:
        """Ingest one or more files. Returns one Asset per input path.

        Bug B regression: empty paths list is rejected with a `fix:` line.
        Bug-hunt #6: each ingested asset is persisted to a sidecar JSON
        so that subsequent ``get()`` calls return full metadata, not
        placeholder values.

        v1.4 P1-1: ``license`` and ``attribution`` are propagated to
        every ``Asset`` produced (and the sidecar JSON). Both default
        to empty strings; callers that ingest third-party media should
        pass them through so the credit line is visible later.
        """
        if not paths:
            raise ValueError(
                "Cannot ingest empty paths list. "
                "fix: provide at least one file path."
            )

        assets: list[Asset] = []
        for p in paths:
            src = Path(p)
            if not src.exists():
                raise FileNotFoundError(p)
            asset_hash = _hash_file(src)
            dest = self._cas_path(asset_hash)
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                shutil.copy2(src, dest)
            media_info = _probe_media(str(src))
            alignment = transcribe(src) if media_info["has_audio"] else []
            asset = Asset(
                asset_hash=asset_hash,
                original_path=str(src),
                stored_path=str(dest),
                type=media_info["type"],
                duration_sec=media_info["duration_sec"],
                fps=media_info["fps"],
                width=media_info["width"],
                height=media_info["height"],
                codec=media_info["codec"],
                has_audio=media_info["has_audio"],
                alignment=alignment,
                license=license,
                attribution=attribution,
            )
            sidecar = self._sidecar_path(asset_hash)
            sidecar.write_text(asset.model_dump_json(indent=2))
            assets.append(asset)
        return assets

    def get(self, asset_hash: str) -> Optional[Asset]:
        path = self._cas_path(asset_hash)
        if not path.exists():
            return None
        sidecar = self._sidecar_path(asset_hash)
        if sidecar.exists():
            return Asset.model_validate_json(sidecar.read_text())
        media_info = _probe_media(str(path))
        return Asset(
            asset_hash=asset_hash,
            original_path="",
            stored_path=str(path),
            type=media_info["type"],
            duration_sec=media_info["duration_sec"],
            fps=media_info["fps"],
            width=media_info["width"],
            height=media_info["height"],
            codec=media_info["codec"],
            has_audio=media_info["has_audio"],
        )

    def path(self, asset_hash: str) -> Optional[Path]:
        p = self._cas_path(asset_hash)
        return p if p.exists() else None
