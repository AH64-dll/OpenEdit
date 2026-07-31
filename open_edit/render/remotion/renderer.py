"""Remotion subprocess execution: command building, lifecycle, and codec mapping."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from open_edit.render.profiles import RenderProfile
from open_edit.render.remotion.safety import (
    RemotionRenderError,
    composition_cache_key,
    composition_source_bundle,
    resolve_remotion_root,
    validate_entry_point,
)

BRIDGE_PATH = Path(__file__).resolve().parent.parent / "remotion_bridge.mjs"


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


def _alpha_vcodec() -> str:
    """Alpha materialization codec.

    Windows: ProRes 4444 — VP8/WebM alpha is unreliable with ffmpeg composite.
    Linux/macOS: keep libvpx (WebM alpha) which is lighter and already proven.
    """
    if sys.platform == "win32":
        return "prores_ks"
    return "libvpx"


def remotion_profile_for_mode(mode: Literal["proxy", "final"], alpha: bool = False) -> RenderProfile:
    """Return width/height/fps used for Remotion materialization.

    Proxy keeps 30fps (same as composition timing) so short overlays like
    2.16s intros keep correct duration; only spatial resolution is reduced.
    """
    alpha_vcodec = _alpha_vcodec()
    if mode == "proxy":
        return RenderProfile(
            name="remotion_proxy",
            # Half-res proxy on all platforms; Windows ProRes stays lighter this way.
            width=960,
            height=540,
            frame_rate_num=30,
            frame_rate_den=1,
            vcodec=alpha_vcodec if alpha else "libx264",
        )
    return RenderProfile(
        name="remotion_final",
        width=1920,
        height=1080,
        frame_rate_num=30,
        frame_rate_den=1,
        vcodec=alpha_vcodec if alpha else "libx264",
    )


class RemotionRunner:
    """Run one Remotion composition render as a subprocess.

    Uses ``OPEN_EDIT_REMOTION_BIN`` when set (tests / custom wrappers),
    otherwise ``node remotion_bridge.mjs``.
    """

    def render(
        self,
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
        """Render one Remotion composition to ``output_path``."""
        project_path = Path(project_path).resolve()
        remotion_root = resolve_remotion_root(project_path)
        validate_entry_point(project_path, entry_point)
        composition_source = composition_source_bundle(project_path, composition_id)
        content_hash = composition_cache_key(
            composition_source=composition_source,
            composition_id=composition_id,
            props=props,
            profile=profile,
            alpha=alpha,
            duration_sec=0.0,
        )

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        props_path = output_path.with_suffix(".props.json")
        props_path.write_text(json.dumps(props, sort_keys=True), encoding="utf-8")

        # Remotion CLI codec names (not ffmpeg encoder names).
        use_prores_alpha = alpha and profile.vcodec == "prores_ks"
        use_vp8_alpha = alpha and profile.vcodec == "libvpx"
        if use_prores_alpha:
            codec = "prores"
        elif use_vp8_alpha:
            codec = "vp8"
        else:
            codec = "h264"
        fps = profile.frame_rate_num / max(profile.frame_rate_den, 1)

        alpha_args: list[str] = []
        if use_prores_alpha:
            # Windows-only path today (see _alpha_vcodec).
            alpha_args = [
                "--pixel-format", "yuva444p10le",
                "--image-format", "png",
                "--prores-profile", "4444",
            ]

        concurrency = os.environ.get("OPEN_EDIT_REMOTION_CONCURRENCY", "").strip()
        if not concurrency:
            # Middle ground: use most cores but leave 1 free for melt/ffmpeg.
            concurrency = str(max(2, (os.cpu_count() or 4) - 1))

        cmd = self._build_command(
            remotion_root=remotion_root,
            entry_point=entry_point,
            composition_id=composition_id,
            props_path=props_path,
            output_path=output_path,
            profile=profile,
            fps=fps,
            codec=codec,
            concurrency=concurrency,
            alpha_args=alpha_args,
        )

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
                    self._terminate_process_group(proc)
                    raise RemotionRenderError("remotion render cancelled")
                rc = proc.poll()
                if rc is not None:
                    break
                if time.monotonic() > deadline:
                    self._terminate_process_group(proc)
                    raise RemotionRenderError(f"remotion render timed out after {timeout_s:.0f}s")
                time.sleep(0.05)
            stdout, stderr = proc.communicate(timeout=5)
        except RemotionRenderError:
            raise
        except Exception as exc:
            self._terminate_process_group(proc)
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

    def _build_command(
        self,
        *,
        remotion_root: Path,
        entry_point: str,
        composition_id: str,
        props_path: Path,
        output_path: Path,
        profile: RenderProfile,
        fps: float,
        codec: str,
        concurrency: str,
        alpha_args: list[str],
    ) -> list[str]:
        """Build the render argv: custom binary or ``node remotion_bridge.mjs``."""
        custom_bin = os.environ.get("OPEN_EDIT_REMOTION_BIN", "").strip()
        if custom_bin:
            program = [custom_bin]
        else:
            node = os.environ.get("OPEN_EDIT_NODE_BIN", "node").strip() or "node"
            program = [node, str(BRIDGE_PATH)]
        return [
            *program,
            "--project-root", str(remotion_root),
            "--entry-point", entry_point,
            "--composition-id", composition_id,
            "--props-file", str(props_path),
            "--output", str(output_path),
            "--width", str(profile.width),
            "--height", str(profile.height),
            "--fps", str(int(fps) if fps == int(fps) else fps),
            "--codec", codec,
            "--concurrency", concurrency,
            *alpha_args,
        ]

    def _terminate_process_group(self, proc: subprocess.Popen[str]) -> None:
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
    """Render one Remotion composition to ``output_path`` (see ``RemotionRunner``)."""
    return RemotionRunner().render(
        project_path,
        entry_point=entry_point,
        composition_id=composition_id,
        props=props,
        output_path=output_path,
        profile=profile,
        timeout_s=timeout_s,
        alpha=alpha,
        cancel_event=cancel_event,
    )
