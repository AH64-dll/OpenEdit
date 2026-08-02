"""Remotion subprocess execution: command building, lifecycle, and codec mapping."""
from __future__ import annotations

import json
import os
import signal
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from open_edit.render.profiles import RenderProfile
from open_edit.render.remotion.safety import (
    ALPHA_POLICY_VERSION,
    RemotionRenderError,
    composition_cache_key,
    composition_source_bundle,
    resolve_remotion_root,
    stage_referenced_assets,
    validate_entry_point,
)

BRIDGE_PATH = Path(__file__).resolve().parent.parent / "remotion_bridge.mjs"


def remotion_worker_count() -> int:
    """Return the bounded number of concurrent Remotion subprocesses."""
    raw = os.environ.get("OPEN_EDIT_REMOTION_WORKERS", "2").strip()
    try:
        requested = int(raw)
    except ValueError:
        return 2
    if requested <= 0:
        return 2
    return min(4, requested)


def _default_remotion_concurrency() -> str:
    """Share the host CPU budget across the bounded worker pool."""
    workers = remotion_worker_count()
    return str(max(1, (os.cpu_count() or 4) // workers))


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


@lru_cache(maxsize=1)
def probe_alpha_capability() -> bool:
    """Verify that this FFmpeg build can decode and composite VP8 alpha.

    Encoding a WebM file is not sufficient: some FFmpeg builds report an
    alpha tag but expose the decoded frames as opaque ``yuv420p``. The probe
    therefore creates a tiny half-transparent VP8 frame and composites it
    over blue, rejecting the common all-red opaque result.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False
    try:
        with tempfile.TemporaryDirectory(prefix="open-edit-alpha-") as td:
            overlay_path = Path(td) / "probe.webm"
            encode = subprocess.run(
                [
                    ffmpeg, "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i",
                    "color=c=red@0.5:s=8x8:d=0.1",
                    "-frames:v", "1", "-an",
                    "-vf", "format=yuva420p",
                    "-c:v", "libvpx", "-pix_fmt", "yuva420p",
                    "-auto-alt-ref", "0", "-f", "webm", str(overlay_path),
                ],
                capture_output=True, timeout=8,
            )
            if encode.returncode != 0 or not overlay_path.is_file():
                return False
            composite = subprocess.run(
                [
                    ffmpeg, "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", "color=c=blue:s=8x8:d=0.1",
                    "-i", str(overlay_path),
                    "-filter_complex",
                    "[1:v]format=yuva420p[ov];"
                    "[0:v][ov]overlay=shortest=1:format=auto,format=rgb24",
                    "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24",
                    "pipe:1",
                ],
                capture_output=True, timeout=8,
            )
            if composite.returncode != 0 or len(composite.stdout) < 3:
                return False
            # Opaque VP8 decoding produces pure red here. Blue or a blended
            # red/blue pixel means the alpha plane survived the round trip.
            pixels = composite.stdout
            return any(
                not (pixels[i] > 245 and pixels[i + 1] < 10 and pixels[i + 2] < 10)
                for i in range(0, len(pixels) - 2, 3)
            )
    except (OSError, subprocess.SubprocessError):
        return False


def resolve_alpha_mode(requested: str | None = None) -> str:
    """Resolve ``auto`` to a verified alpha codec, never a guess."""
    raw = (
        requested
        or os.environ.get("OPEN_EDIT_ALPHA_MODE", "auto")
    ).strip().lower()
    if raw == "auto":
        return "vp8" if probe_alpha_capability() else "prores"
    if raw not in {"prores", "vp8", "vp9"}:
        raise ValueError("alpha_mode must be auto, prores, vp8, or vp9")
    return raw


def _alpha_vcodec(alpha_mode: str | None = None) -> str:
    return {
        "prores": "prores_ks",
        "vp8": "libvpx",
        "vp9": "libvpx-vp9",
    }[resolve_alpha_mode(alpha_mode)]


def remotion_profile_for_mode(
    mode: Literal["proxy", "final"],
    alpha: bool = False,
    alpha_mode: str | None = None,
) -> RenderProfile:
    """Return width/height/fps used for Remotion materialization.

    Proxy keeps 30fps (same as composition timing) so short overlays like
    2.16s intros keep correct duration; only spatial resolution is reduced.
    """
    alpha_vcodec = _alpha_vcodec(alpha_mode) if alpha else "libx264"
    if mode == "proxy":
        return RenderProfile(
            name="remotion_proxy",
            # Match the fast proxy dimensions so alpha materialization is not
            # rendered larger than the frame it will be composited into.
            width=640,
            height=360,
            frame_rate_num=30,
            frame_rate_den=1,
            vcodec=alpha_vcodec,
        )
    return RenderProfile(
        name="remotion_final",
        width=1920,
        height=1080,
        frame_rate_num=30,
        frame_rate_den=1,
        vcodec=alpha_vcodec,
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
        stage_assets: bool = True,
    ) -> RemotionRenderResult:
        """Render one Remotion composition to ``output_path``."""
        project_path = Path(project_path).resolve()
        remotion_root = resolve_remotion_root(project_path)
        validate_entry_point(project_path, entry_point)
        composition_source = composition_source_bundle(project_path, composition_id)
        if stage_assets:
            stage_referenced_assets(project_path, composition_source, props)
        content_hash = composition_cache_key(
            composition_source=composition_source,
            composition_id=composition_id,
            props=props,
            profile=profile,
            alpha=alpha,
            duration_sec=0.0,
            project_path=project_path,
        )

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        props_path = output_path.with_suffix(".props.json")
        props_path.write_text(json.dumps(props, sort_keys=True), encoding="utf-8")

        # Remotion CLI codec names (not ffmpeg encoder names).
        use_prores_alpha = alpha and profile.vcodec == "prores_ks"
        use_vp8_alpha = alpha and profile.vcodec == "libvpx"
        use_vp9_alpha = alpha and profile.vcodec == "libvpx-vp9"
        if use_prores_alpha:
            codec = "prores"
        elif use_vp8_alpha or use_vp9_alpha:
            codec = "vp9" if use_vp9_alpha else "vp8"
        else:
            codec = "h264"
        fps = profile.frame_rate_num / max(profile.frame_rate_den, 1)

        alpha_args: list[str] = []
        if use_vp8_alpha or use_vp9_alpha:
            alpha_args = [
                "--pixel-format", "yuva420p",
                "--image-format", "png",
            ]
        elif use_prores_alpha:
            # ProRes is the correctness fallback when VP8/VP9 alpha probing
            # cannot prove transparent pixels survive this FFmpeg build.
            alpha_args = [
                "--pixel-format", "yuva444p10le",
                "--image-format", "png",
                "--prores-profile", "4444",
            ]

        concurrency = os.environ.get("OPEN_EDIT_REMOTION_CONCURRENCY", "").strip()
        if not concurrency:
            concurrency = _default_remotion_concurrency()

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
    stage_assets: bool = True,
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
        stage_assets=stage_assets,
    )
