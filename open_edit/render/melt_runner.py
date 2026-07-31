"""Melt subprocess execution: command building, timeout, and cache mediation."""
from __future__ import annotations

import dataclasses
import os
import subprocess
from pathlib import Path
from typing import Optional

from open_edit.render.cache import RenderCache
from open_edit.render.pipe_builder import PipeCommands
from open_edit.render.profiles import RenderProfile, profile_to_mlt_args


class MeltTimeoutError(Exception):
    """Raised when melt exceeds its wall-clock budget."""


class MeltRunner:
    """Build and run melt commands, mediating the render cache.

    Cache lookup happens before emit (fresh hits short-circuit the render);
    ``cache_put`` stores the final MP4 after overlay burning.
    """

    def __init__(
        self,
        melt_bin: str,
        cache: Optional[RenderCache] = None,
        nice_level: int = 10,
        encoder_backend: Optional[str] = None,
    ):
        self.melt_bin = melt_bin
        self.cache = cache
        self.nice_level = nice_level
        self.encoder_backend = encoder_backend

    def cached(self, key: str) -> Optional[Path]:
        """Look up a cached render for ``key`` (None if absent)."""
        if self.cache is None:
            return None
        return self.cache.get(key)

    def is_fresh(self, path: Path) -> bool:
        """True if the cached file is younger than the cache freshness window."""
        if self.cache is None:
            return False
        return self.cache.is_fresh(path)

    def cache_put(self, key: str, source_path: str | Path) -> Path:
        """Copy ``source_path`` into the cache under ``key``. Returns the cached path."""
        if self.cache is None:
            return Path(source_path)
        return self.cache.put(key, source_path)

    def build_command(
        self,
        xml_path: Path,
        output_mp4: Path,
        profile: RenderProfile,
        mode: str = "proxy",
    ) -> list[str]:
        """Build the melt command line."""
        args = [self.melt_bin, str(xml_path), "-consumer", f"avformat:{output_mp4}"]
        args += profile_to_mlt_args(profile, backend=self.encoder_backend, mode=mode)
        if self.nice_level > 0 and os.name == "posix":
            return ["nice", "-n", str(self.nice_level)] + args
        return args

    def run(
        self,
        xml_path: Path,
        output_mp4: Path,
        profile: RenderProfile,
        mode: str,
        timeout_s: float,
    ) -> subprocess.CompletedProcess:
        """Run melt against ``xml_path``; raise MeltTimeoutError on timeout."""
        cmd = self.build_command(xml_path, output_mp4, profile, mode=mode)
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
        except subprocess.TimeoutExpired as exc:
            raise MeltTimeoutError(f"melt timed out after {timeout_s:g}s") from exc


class PipeRunError(RuntimeError):
    """Raised when a frame-server pipe fails or exceeds its wall-clock budget."""


@dataclasses.dataclass
class PipeResult:
    """Outcome of a frame-server pipe run."""
    returncode: int
    melt_rc: int
    ffmpeg_rc: int
    stderr: str


def run_pipe(cmds: PipeCommands, *, timeout_s: float) -> PipeResult:
    """Run melt (video -> raw pipe) and ffmpeg concurrently; audio pass first.

    stderr of both processes is captured via temp files (no pipe-buffer
    deadlock) and merged with ``melt:`` / ``ffmpeg:`` labels. ffmpeg's
    exit drives the result; a melt failure aborts before ffmpeg starts.
    """
    import subprocess
    import tempfile
    import time as _time

    def _exec_sync(cmd: list[str], label: str) -> tuple[int, str]:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
        return proc.returncode, proc.stderr or ""

    # 1) Audio pass first (fast: video_off=1). ffmpeg opens it at startup.
    try:
        audio_rc, audio_err = _exec_sync(cmds.melt_audio_cmd, "melt-audio")
    except subprocess.TimeoutExpired:
        raise PipeRunError(f"melt-audio timed out after {timeout_s:g}s") from None
    if audio_rc != 0:
        return PipeResult(audio_rc, audio_rc, -1, f"melt-audio failed:\n{audio_err.strip()}")

    # 2) Video pipe: melt -> ffmpeg.
    deadline = _time.monotonic() + timeout_s
    with tempfile.TemporaryFile() as melt_err_f, tempfile.TemporaryFile() as ff_err_f:
        try:
            melt = subprocess.Popen(
                cmds.melt_video_cmd, stdout=subprocess.PIPE, stderr=melt_err_f,
            )
            ffmpeg = subprocess.Popen(
                cmds.ffmpeg_cmd, stdin=melt.stdout, stderr=ff_err_f,
            )
        except OSError as exc:
            raise PipeRunError(f"pipe spawn failed: {exc}") from None
        melt.stdout.close()
        try:
            ffmpeg_rc = ffmpeg.wait(timeout=max(0.5, deadline - _time.monotonic()))
        except subprocess.TimeoutExpired:
            melt.kill()
            ffmpeg.kill()
            melt.wait()
            ffmpeg.wait()
            raise PipeRunError(f"render pipe timed out after {timeout_s:g}s") from None
        try:
            melt_rc = melt.wait(timeout=30)
        except subprocess.TimeoutExpired:
            melt.kill()
            melt_rc = melt.wait()
        melt_err_f.seek(0)
        ff_err_f.seek(0)
        melt_err = melt_err_f.read().decode("utf-8", errors="replace").strip()
        ff_err = ff_err_f.read().decode("utf-8", errors="replace").strip()

    stderr = "\n".join(
        part for part in (
            f"melt (rc={melt_rc}): {melt_err[-400:]}" if melt_err else "",
            f"ffmpeg (rc={ffmpeg_rc}): {ff_err[-400:]}" if ff_err else "",
        ) if part
    )
    # ffmpeg's rc wins when it failed (melt usually dies of broken pipe then);
    # otherwise surface melt's failure (fake-ffmpeg succeeded but melt broke).
    if ffmpeg_rc != 0:
        return PipeResult(ffmpeg_rc, melt_rc, ffmpeg_rc, stderr)
    if melt_rc != 0:
        return PipeResult(melt_rc, melt_rc, ffmpeg_rc, stderr)
    return PipeResult(0, 0, 0, stderr)
