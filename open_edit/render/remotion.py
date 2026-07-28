"""Remotion composition renderer for Open Edit.

Materializes React Remotion compositions to media files that are then
ingested into the CAS and treated as normal MLT clips. Never shell-
interpolates props: they are always written to a JSON file.
"""
from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from open_edit.render.profiles import RenderProfile

REMOTION_VERSION = "4.0.278"
BRIDGE_PATH = Path(__file__).resolve().parent / "remotion_bridge.mjs"


class RemotionRenderError(RuntimeError):
    """Raised when a Remotion composition cannot be rendered."""


@dataclass(frozen=True)
class RemotionRenderResult:
    ok: bool
    output_path: str
    width: int
    height: int
    fps: float
    content_hash: str
    duration_sec: float = 0.0
    error: str | None = None


def remotion_profile_for_mode(mode: Literal["proxy", "final"], alpha: bool = False) -> RenderProfile:
    """Return width/height/fps used for Remotion materialization."""
    if mode == "proxy":
        return RenderProfile(
            name="remotion_proxy",
            width=1280,
            height=720,
            frame_rate_num=15,
            frame_rate_den=1,
            vcodec="libvpx" if alpha else "libx264",
        )
    return RenderProfile(
        name="remotion_final",
        width=1920,
        height=1080,
        frame_rate_num=30,
        frame_rate_den=1,
        vcodec="libvpx" if alpha else "libx264",
    )


def resolve_remotion_root(project_path: Path) -> Path:
    """Return ``<project>/.open_edit/remotion``."""
    return (project_path / ".open_edit" / "remotion").resolve()


def validate_entry_point(project_path: Path, entry_point: str) -> Path:
    """Ensure entry_point stays under ``.open_edit/remotion/``."""
    root = resolve_remotion_root(project_path)
    if not entry_point or entry_point.startswith(("/", "\\")) or ".." in Path(entry_point).parts:
        raise RemotionRenderError(
            f"entry_point must be relative under .open_edit/remotion/; got {entry_point!r}"
        )
    candidate = (root / entry_point).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise RemotionRenderError(
            f"entry_point escapes remotion root: {entry_point!r}"
        ) from exc
    if not candidate.is_file():
        raise RemotionRenderError(f"entry_point not found: {entry_point}")
    return candidate


def composition_cache_key(
    *,
    entry_source: str,
    composition_id: str,
    props: dict[str, Any],
    profile: RenderProfile,
    alpha: bool,
) -> str:
    payload = {
        "entry_source": entry_source,
        "composition_id": composition_id,
        "props": props,
        "profile": profile.model_dump(),
        "alpha": alpha,
        "remotion_version": REMOTION_VERSION,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def render_composition(
    project_path: Path,
    *,
    entry_point: str,
    composition_id: str,
    props: dict[str, Any],
    output_path: Path,
    profile: RenderProfile,
    timeout_s: float = 600.0,
    alpha: bool = False,
    cancel_event: Any | None = None,
) -> RemotionRenderResult:
    """Render one Remotion composition to ``output_path``.

    Uses ``OPEN_EDIT_REMOTION_BIN`` when set (tests / custom wrappers),
    otherwise ``node remotion_bridge.mjs``.
    """
    project_path = Path(project_path).resolve()
    remotion_root = resolve_remotion_root(project_path)
    entry_abs = validate_entry_point(project_path, entry_point)
    entry_source = entry_abs.read_text(encoding="utf-8")
    content_hash = composition_cache_key(
        entry_source=entry_source,
        composition_id=composition_id,
        props=props,
        profile=profile,
        alpha=alpha,
    )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    props_path = output_path.with_suffix(".props.json")
    props_path.write_text(json.dumps(props, sort_keys=True), encoding="utf-8")

    codec = "vp8" if alpha else "h264"
    fps = profile.frame_rate_num / max(profile.frame_rate_den, 1)

    custom_bin = os.environ.get("OPEN_EDIT_REMOTION_BIN", "").strip()
    if custom_bin:
        cmd = [
            custom_bin,
            "--project-root", str(remotion_root),
            "--entry-point", entry_point,
            "--composition-id", composition_id,
            "--props-file", str(props_path),
            "--output", str(output_path),
            "--width", str(profile.width),
            "--height", str(profile.height),
            "--fps", str(int(fps) if fps == int(fps) else fps),
            "--codec", codec,
        ]
    else:
        node = os.environ.get("OPEN_EDIT_NODE_BIN", "node").strip() or "node"
        cmd = [
            node,
            str(BRIDGE_PATH),
            "--project-root", str(remotion_root),
            "--entry-point", entry_point,
            "--composition-id", composition_id,
            "--props-file", str(props_path),
            "--output", str(output_path),
            "--width", str(profile.width),
            "--height", str(profile.height),
            "--fps", str(int(fps) if fps == int(fps) else fps),
            "--codec", codec,
        ]

    kwargs: dict[str, Any] = {
        "cwd": str(remotion_root),
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
    }
    if os.name == "posix":
        kwargs["start_new_session"] = True

    try:
        proc = subprocess.Popen(cmd, **kwargs)
    except FileNotFoundError as exc:
        raise RemotionRenderError(f"remotion binary not found: {exc}") from exc

    deadline = time.monotonic() + timeout_s
    try:
        while True:
            if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
                _terminate_process_group(proc)
                raise RemotionRenderError("remotion render cancelled")
            rc = proc.poll()
            if rc is not None:
                break
            if time.monotonic() > deadline:
                _terminate_process_group(proc)
                raise RemotionRenderError(f"remotion render timed out after {timeout_s:.0f}s")
            time.sleep(0.05)
        stdout, stderr = proc.communicate(timeout=5)
    except RemotionRenderError:
        raise
    except Exception as exc:
        _terminate_process_group(proc)
        raise RemotionRenderError(str(exc)) from exc

    if proc.returncode != 0:
        detail = (stderr or stdout or "").strip().splitlines()
        raise RemotionRenderError(
            detail[-1] if detail else f"remotion exited {proc.returncode}"
        )

    # Prefer structured JSON from the bridge when present.
    parsed: dict[str, Any] = {}
    for line in reversed((stdout or "").splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                parsed = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
    if parsed.get("ok") is False:
        raise RemotionRenderError(str(parsed.get("error") or "remotion reported failure"))

    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RemotionRenderError("remotion produced no output file")

    return RemotionRenderResult(
        ok=True,
        output_path=str(output_path),
        width=int(parsed.get("width") or profile.width),
        height=int(parsed.get("height") or profile.height),
        fps=float(parsed.get("fps") or fps),
        content_hash=content_hash,
    )


def _terminate_process_group(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGTERM)
        else:
            proc.terminate()
        try:
            proc.wait(timeout=5)
            return
        except subprocess.TimeoutExpired:
            pass
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
        proc.wait(timeout=5)
    except (ProcessLookupError, OSError):
        return
