"""Native HyperFrames composition materialization for Open Edit."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from open_edit.ir.types import Timeline
from open_edit.render.html_overlay import generate_composition_html, render_overlay_layer


class HyperFramesRenderError(RuntimeError):
    """Raised when a HyperFrames composition cannot be materialized."""


@dataclass(frozen=True)
class HyperFramesMaterializeResult:
    output_path: Path
    cache_hit: bool
    content_hash: str
    elapsed_sec: float


def _hyperframes_bin() -> str:
    configured = os.environ.get("OPEN_EDIT_HYPERFRAMES_BIN", "").strip()
    if configured:
        return configured
    repo_bin = Path(__file__).resolve().parents[2] / "node_modules" / ".bin" / "hyperframes"
    if repo_bin.is_file():
        return str(repo_bin)
    installed = shutil.which("hyperframes")
    if installed:
        return installed
    raise HyperFramesRenderError(
        "HyperFrames binary not found; install pinned hyperframes or set "
        "OPEN_EDIT_HYPERFRAMES_BIN"
    )


def hyperframes_reference_fingerprint(
    timeline: Timeline,
    project_path: Path,
    *,
    mode: Literal["proxy", "final"] = "proxy",
    width: int,
    height: int,
    fps: float,
) -> str:
    if not timeline.overlays:
        return "none"
    spec = {
        "mode": mode,
        "width": width,
        "height": height,
        "fps": fps,
        "html": generate_composition_html(
            timeline,
            Path(project_path),
            {
                "width": width,
                "height": height,
                "fps": fps,
                "duration_sec": timeline.duration_sec,
            },
        ),
        "version": "hyperframes-native-v1",
    }
    return hashlib.sha256(
        json.dumps(spec, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def materialize_hyperframes_overlays(
    timeline: Timeline,
    project_path: Path,
    *,
    mode: Literal["proxy", "final"] = "proxy",
    width: int,
    height: int,
    fps: float,
    force: bool = False,
) -> HyperFramesMaterializeResult | None:
    if not timeline.overlays:
        return None
    started = time.monotonic()
    project_path = Path(project_path).resolve()
    content_hash = hyperframes_reference_fingerprint(
        timeline,
        project_path,
        mode=mode,
        width=width,
        height=height,
        fps=fps,
    )
    output_dir = project_path / ".open_edit" / "hyperframes" / "out" / mode
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"overlay_{content_hash[:24]}.mov"
    if not force and output_path.is_file() and output_path.stat().st_size > 0:
        return HyperFramesMaterializeResult(
            output_path=output_path,
            cache_hit=True,
            content_hash=content_hash,
            elapsed_sec=time.monotonic() - started,
        )

    tmpdir = project_path / ".open_edit" / "hyperframes" / "tmp" / content_hash
    tmpdir.mkdir(parents=True, exist_ok=True)
    composition_path = tmpdir / "composition.html"
    composition_path.write_text(
        generate_composition_html(
            timeline,
            project_path,
            {
                "width": width,
                "height": height,
                "fps": fps,
                "duration_sec": timeline.duration_sec,
            },
        ),
        encoding="utf-8",
    )
    try:
        render_overlay_layer(
            composition_path,
            output_path,
            {
                "width": width,
                "height": height,
                "fps": fps,
                "duration_sec": timeline.duration_sec,
                "tmpdir": tmpdir,
                "hyperframes_bin": _hyperframes_bin(),
                "hyperframes_timeout_s": int(
                    os.environ.get("OPEN_EDIT_HYPERFRAMES_TIMEOUT_SECONDS", "3600")
                ),
            },
        )
    except Exception as exc:
        output_path.unlink(missing_ok=True)
        raise HyperFramesRenderError(str(exc)) from exc
    finally:
        composition_path.unlink(missing_ok=True)
        shutil.rmtree(tmpdir, ignore_errors=True)

    _evict_hyperframes_cache(output_dir, output_path)
    return HyperFramesMaterializeResult(
        output_path=output_path,
        cache_hit=False,
        content_hash=content_hash,
        elapsed_sec=time.monotonic() - started,
    )


def _evict_hyperframes_cache(output_dir: Path, newest: Path) -> None:
    raw_cap = os.environ.get("OPEN_EDIT_HYPERFRAMES_CACHE_MAX_BYTES", "536870912")
    try:
        cap = max(0, int(raw_cap))
    except ValueError:
        cap = 512 * 1024 * 1024
    entries = [
        path for path in output_dir.glob("*.mov")
        if path.is_file() and path != newest
    ]
    total = sum(path.stat().st_size for path in entries + [newest] if path.is_file())
    if total <= cap:
        return
    entries.sort(key=lambda path: (path.stat().st_mtime, path.name))
    for path in entries:
        if total <= cap:
            break
        try:
            total -= path.stat().st_size
            path.unlink()
        except OSError:
            continue


__all__ = [
    "HyperFramesMaterializeResult",
    "HyperFramesRenderError",
    "hyperframes_reference_fingerprint",
    "materialize_hyperframes_overlays",
]
