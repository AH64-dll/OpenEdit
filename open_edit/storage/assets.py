"""Content-addressed asset store with ffprobe metadata.

Layout: <assets_dir>/<sha256[:2]>/<sha256>
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from open_edit.ir.ids import now_iso8601
from open_edit.ir.types import Asset, SourceProxyStatus
from open_edit.storage.transcription import transcribe


CHUNK_SIZE = 65536

_LOG = logging.getLogger("open_edit.storage.assets")
_IMAGE_EXTENSIONS = {
    ".avif", ".bmp", ".gif", ".jpeg", ".jpg", ".png", ".svg", ".tif", ".tiff", ".webp",
}


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

    try:
        fmt_result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_format", "-show_streams",
                "-of", "json", str(src),
            ],
            capture_output=True, text=True, check=True,
        )
    except FileNotFoundError as e:
        raise RuntimeError("FFmpeg/ffprobe is missing from PATH. Please install it.") from e
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffprobe failed: {e.stderr.strip() or e.stdout.strip()}") from e

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
    pix_fmt = video_stream.get("pix_fmt") if video_stream else None
    pix_fmt_lower = (pix_fmt or "").lower()
    has_alpha = any(
        marker in pix_fmt_lower
        for marker in (
            "alpha", "rgba", "bgra", "argb", "abgr", "yuva", "ayuv", "gbrap", "ya",
        )
    )

    if src.suffix.lower() in _IMAGE_EXTENSIONS:
        media_type = "image"
    elif audio_stream and not video_stream:
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
        "pix_fmt": pix_fmt,
        "has_alpha": has_alpha,
        "has_audio": audio_stream is not None,
        "type": media_type,
    }


def source_proxy_auto_enqueue_enabled() -> bool:
    """Whether ingest should auto-enqueue source-proxy generation.

    Default **on**: proxies are needed by the ``proxy`` emission policies
    (proxy-edit, preview-chunk), so starting generation at ingest time lets
    the durable queue fill idle time. Set ``OPEN_EDIT_SOURCE_PROXY_AUTO=0``
    (or ``false``/``no``/``off``) to disable; the queue still runs when the
    render path asks for a proxy.
    """
    raw = os.environ.get("OPEN_EDIT_SOURCE_PROXY_AUTO")
    if raw is None or not str(raw).strip():
        return True
    return str(raw).strip().lower() not in ("0", "false", "no", "off")


def _maybe_enqueue_source_proxy(assets_dir: Path, asset: Asset) -> None:
    """Best-effort, non-blocking background source-proxy enqueue.

    Never raises and never blocks ingest: proxy generation is a durable
    queue job with bounded concurrency, and ingest success must not depend
    on it. Cheap eligibility pre-checks mirror ``generate_asset_proxy``'s
    own shortcuts so images/audio/small/alpha sources don't create rows.
    """
    if not source_proxy_auto_enqueue_enabled():
        return
    if asset.type != "video" or asset.has_alpha or asset.proxy_status == "ready":
        return
    try:
        from open_edit.render.source_proxy import DEFAULT_SOURCE_PROXY_PROFILE

        if (
            asset.height is not None
            and asset.height <= DEFAULT_SOURCE_PROXY_PROFILE.height
        ):
            return
        # The canonical layout is <root>/.open_edit/assets; the legacy layout
        # is <root>/assets. Mirrors timeline_plan's project-path derivation.
        parent = Path(assets_dir).parent
        project_path = parent.parent if parent.name == ".open_edit" else parent

        from open_edit.kernel.asset_proxy_jobs import (
            DEFAULT_ASSET_PROXY_JOB_SERVICE,
        )

        DEFAULT_ASSET_PROXY_JOB_SERVICE.enqueue(
            project_path.name,
            project_path,
            asset.asset_hash,
            profile=DEFAULT_SOURCE_PROXY_PROFILE,
        )
    except Exception:
        # A proxy error (DB lock, missing ffmpeg, race) must never fail the
        # ingest that just succeeded.
        _LOG.debug("source proxy auto-enqueue skipped", exc_info=True)


def list_assets_from_disk(project_path: Path) -> list[Asset]:
    """Read all asset sidecar JSONs from <project>/assets/."""
    assets_dir = project_path / ".open_edit" / "assets"
    if not assets_dir.exists():
        # Fallback to project root's assets dir (older layout)
        assets_dir = project_path / "assets"
    if not assets_dir.exists():
        return []
    out: list[Asset] = []
    for meta_file in assets_dir.glob("*/*.meta.json"):
        try:
            out.append(Asset.model_validate_json(meta_file.read_text()))
        except Exception:
            # v1.6 P4: a corrupt sidecar used to be silently dropped
            # (indistinguishable from "no asset here"). Log it so the
            # operator can see *why* an asset is missing in the UI.
            _LOG.warning(
                "failed to parse asset sidecar %s; skipping",
                meta_file, exc_info=True,
            )
            continue
    return out


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

    def ingest(
        self,
        source_path: str,
        transcribe: bool = True,
        *,
        license: str = "",
        attribution: str = "",
        provider: str = "",
        source_url: str = "",
        source_page_url: str = "",
    ) -> Asset:
        return self.ingest_paths(
            [source_path],
            license=license,
            attribution=attribution,
            do_transcribe=transcribe,
            provider=provider,
            source_url=source_url,
            source_page_url=source_page_url,
        )[0]

    def ingest_paths(
        self, paths: list[str],
        license: str = "",
        attribution: str = "",
        do_transcribe: bool = True,
        provider: str = "",
        source_url: str = "",
        source_page_url: str = "",
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
            
            copied = False
            if not dest.exists():
                shutil.copy2(src, dest)
                copied = True
                
            try:
                media_info = _probe_media(str(src))
                alignment = (
                    transcribe(src) if (do_transcribe and media_info.get("has_audio", False)) else []
                )
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
                    has_audio=media_info.get("has_audio", False),
                    pix_fmt=media_info.get("pix_fmt"),
                    has_alpha=media_info.get("has_alpha", False),
                    alignment=alignment,
                    license=license,
                    attribution=attribution,
                    content_hash=asset_hash,
                    provider=provider,
                    source_url=source_url,
                    source_page_url=source_page_url,
                )
                sidecar = self._sidecar_path(asset_hash)
                sidecar.write_text(asset.model_dump_json(indent=2))
                _maybe_enqueue_source_proxy(self.assets_dir, asset)
                assets.append(asset)
            except Exception:
                if copied:
                    dest.unlink(missing_ok=True)
                raise
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
            has_audio=media_info.get("has_audio", False),
            pix_fmt=media_info.get("pix_fmt"),
            has_alpha=media_info.get("has_alpha", False),
            content_hash=asset_hash,
        )

    def path(self, asset_hash: str) -> Optional[Path]:
        p = self._cas_path(asset_hash)
        return p if p.is_file() else None

    def store_derived(self, source_path: str | Path) -> str:
        """Store a completed derived file in the CAS without a sidecar."""
        source = Path(source_path)
        if not source.is_file():
            raise FileNotFoundError(source)
        if source.stat().st_size == 0:
            raise ValueError(f"derived file is empty: {source}")

        asset_hash = _hash_file(source)
        destination = self._cas_path(asset_hash)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if not destination.is_file():
                raise IsADirectoryError(destination)
            return asset_hash

        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=destination.parent,
                prefix=f".{destination.name}.",
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
            shutil.copyfile(source, temporary)
            os.replace(temporary, destination)
            temporary = None
            return asset_hash
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def update_proxy_metadata(
        self,
        asset_hash: str,
        *,
        proxy_hash: str | None,
        profile: str | None,
        status: SourceProxyStatus,
        error: str = "",
    ) -> Asset:
        """Atomically update only source-proxy fields on an asset sidecar."""
        asset = self.get(asset_hash)
        if asset is None:
            raise FileNotFoundError(asset_hash)
        updated = asset.model_copy(
            update={
                "proxy_hash": proxy_hash,
                "proxy_profile": profile,
                "proxy_status": status,
                "proxy_error": error,
                "proxy_updated_at": now_iso8601(),
            }
        )
        sidecar = self._sidecar_path(asset_hash)
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=sidecar.parent,
                prefix=f".{sidecar.name}.",
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                handle.write(updated.model_dump_json(indent=2))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, sidecar)
            temporary = None
            return updated
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def clear_proxy_metadata(self, asset_hash: str) -> Asset:
        """Clear source-proxy linkage and reset its status to ``none``."""
        return self.update_proxy_metadata(
            asset_hash,
            proxy_hash=None,
            profile=None,
            status="none",
        )

    def update_alignment(self, asset_hash: str, alignment: list) -> None:
        """Rewrite an asset's sidecar with new word-level ``alignment``.

        Used by background transcription so an upload can return immediately
        with an empty alignment and be enriched once Whisper finishes.
        """
        asset = self.get(asset_hash)
        if asset is None:
            raise FileNotFoundError(asset_hash)
        asset = asset.model_copy(update={"alignment": alignment})
        sidecar = self._sidecar_path(asset_hash)
        sidecar.write_text(asset.model_dump_json(indent=2))
