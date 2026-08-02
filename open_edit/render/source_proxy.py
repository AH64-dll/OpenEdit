"""Per-asset low-resolution source-proxy generation."""
from __future__ import annotations

import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from open_edit.ir.types import SourceProxyStatus
from open_edit.storage.assets import AssetStore


@dataclass(frozen=True)
class SourceProxyProfile:
    name: str
    height: int
    vcodec: str
    crf: int
    preset: str
    acodec: str
    audio_bitrate: str
    version: int

    def fingerprint(self) -> str:
        return (
            f"{self.name}:v{self.version}:h{self.height}:"
            f"{self.vcodec}:crf={self.crf}:preset={self.preset}:"
            f"{self.acodec}:{self.audio_bitrate}"
        )


DEFAULT_SOURCE_PROXY_PROFILE = SourceProxyProfile(
    name="source_proxy_360_v1",
    height=360,
    vcodec="libx264",
    crf=28,
    preset="veryfast",
    acodec="aac",
    audio_bitrate="96k",
    version=1,
)


@dataclass(frozen=True)
class SourceProxyResult:
    asset_hash: str
    proxy_hash: str | None
    profile: str
    status: SourceProxyStatus
    output_path: str | None
    elapsed_sec: float
    error: str | None = None


def _elapsed(started: float) -> float:
    return time.monotonic() - started


def _text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode(errors="replace").strip()
    return str(value or "").strip()


def _failure(
    asset_hash: str,
    profile: SourceProxyProfile,
    started: float,
    error: str,
) -> SourceProxyResult:
    return SourceProxyResult(
        asset_hash=asset_hash,
        proxy_hash=None,
        profile=profile.name,
        status="failed",
        output_path=None,
        elapsed_sec=_elapsed(started),
        error=error,
    )


def _record_failure(
    store: AssetStore,
    asset_hash: str,
    profile: SourceProxyProfile,
    error: str,
) -> None:
    try:
        store.update_proxy_metadata(
            asset_hash,
            proxy_hash=None,
            profile=profile.name,
            status="failed",
            error=error,
        )
    except Exception:
        # The original generation error is more useful than a sidecar write
        # error, and a missing/corrupt asset may not have a sidecar to update.
        pass


def generate_asset_proxy(
    project_path: Path,
    asset_hash: str,
    *,
    profile: SourceProxyProfile = DEFAULT_SOURCE_PROXY_PROFILE,
    timeout_s: float | None = None,
) -> SourceProxyResult:
    """Generate or reuse one low-resolution source-proxy CAS object."""
    started = time.monotonic()
    store = AssetStore(Path(project_path) / ".open_edit" / "assets")

    try:
        asset = store.get(asset_hash)
    except Exception as exc:
        error = f"failed to load asset {asset_hash}: {exc}"
        _record_failure(store, asset_hash, profile, error)
        return _failure(asset_hash, profile, started, error)

    if asset is None:
        error = f"canonical asset bytes are missing: {asset_hash}"
        return _failure(asset_hash, profile, started, error)

    source_path = store.path(asset_hash)
    if source_path is None:
        error = f"canonical asset bytes are missing: {asset_hash}"
        _record_failure(store, asset_hash, profile, error)
        return _failure(asset_hash, profile, started, error)

    if (
        asset.type != "video"
        or asset.has_alpha
        or (asset.height is not None and asset.height <= profile.height)
    ):
        store.update_proxy_metadata(
            asset_hash,
            proxy_hash=None,
            profile=None,
            status="not_needed",
        )
        return SourceProxyResult(
            asset_hash=asset_hash,
            proxy_hash=None,
            profile=profile.name,
            status="not_needed",
            output_path=None,
            elapsed_sec=_elapsed(started),
        )

    if (
        asset.proxy_status == "ready"
        and asset.proxy_profile == profile.name
        and asset.proxy_hash
    ):
        proxy_path = store.path(asset.proxy_hash)
        if proxy_path is not None and proxy_path.is_file():
            return SourceProxyResult(
                asset_hash=asset_hash,
                proxy_hash=asset.proxy_hash,
                profile=profile.name,
                status="ready",
                output_path=str(proxy_path),
                elapsed_sec=_elapsed(started),
            )

    try:
        store.update_proxy_metadata(
            asset_hash,
            proxy_hash=None,
            profile=profile.name,
            status="running",
        )
    except Exception as exc:
        error = f"failed to mark source proxy running: {exc}"
        return _failure(asset_hash, profile, started, error)

    temp_output: Path | None = None
    try:
        timeout = (
            timeout_s
            if timeout_s is not None
            else max(120.0, asset.duration_sec * 4.0 + 60.0)
        )
        temp_dir = Path(project_path) / ".open_edit" / "tmp" / "source-proxy"
        temp_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=temp_dir,
            prefix="source-proxy-",
            suffix=".mp4",
            delete=False,
        ) as handle:
            temp_output = Path(handle.name)

        command = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(source_path),
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-vf",
            f"scale=w='if(gt(ih,{profile.height}),-2,iw)':"
            f"h='min(ih,{profile.height})'",
            "-c:v",
            profile.vcodec,
            "-preset",
            profile.preset,
            "-crf",
            str(profile.crf),
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            profile.acodec,
            "-b:a",
            profile.audio_bitrate,
            "-movflags",
            "+faststart",
            str(temp_output),
        ]
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        if completed.returncode != 0:
            detail = _text(completed.stderr) or _text(completed.stdout)
            error = f"ffmpeg failed with exit code {completed.returncode}"
            if detail:
                error = f"{error}: {detail}"
            raise RuntimeError(error)
        if not temp_output.is_file() or temp_output.stat().st_size == 0:
            raise RuntimeError("ffmpeg produced an empty source proxy")

        proxy_hash = store.store_derived(temp_output)
        proxy_path = store.path(proxy_hash)
        if proxy_path is None:
            raise RuntimeError("source proxy CAS copy is missing")
        store.update_proxy_metadata(
            asset_hash,
            proxy_hash=proxy_hash,
            profile=profile.name,
            status="ready",
        )
        return SourceProxyResult(
            asset_hash=asset_hash,
            proxy_hash=proxy_hash,
            profile=profile.name,
            status="ready",
            output_path=str(proxy_path),
            elapsed_sec=_elapsed(started),
        )
    except subprocess.TimeoutExpired as exc:
        detail = _text(exc.stderr) or _text(exc.stdout)
        error = f"ffmpeg timed out after {timeout}s"
        if detail:
            error = f"{error}: {detail}"
        _record_failure(store, asset_hash, profile, error)
        return _failure(asset_hash, profile, started, error)
    except Exception as exc:
        error = str(exc) or exc.__class__.__name__
        _record_failure(store, asset_hash, profile, error)
        return _failure(asset_hash, profile, started, error)
    finally:
        if temp_output is not None:
            temp_output.unlink(missing_ok=True)
