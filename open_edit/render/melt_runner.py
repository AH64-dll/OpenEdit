"""Melt subprocess execution: command building, timeout, and cache mediation."""
from __future__ import annotations

import dataclasses
import os
import subprocess
import threading
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Optional

from open_edit.render.cache import RenderCache
from open_edit.render.pipe_builder import PipeCommands
from open_edit.render.profiles import RenderProfile, profile_to_mlt_args
from open_edit.render.remotion.frame_feeder import FrameFeeder, FrameFeederError


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
    elapsed_sec: float = 0.0
    audio_elapsed_sec: float = 0.0
    melt_elapsed_sec: float = 0.0
    ffmpeg_elapsed_sec: float = 0.0
    frames_requested: int = 0
    frame_elapsed_sec: float = 0.0
    frame_error: str = ""


def _frame_fd_is_open(fd: int) -> bool:
    try:
        os.fstat(fd)
    except OSError:
        return False
    return True


def _duplicate_away(fd: int, forbidden: set[int]) -> int:
    duplicate = os.dup(fd)
    while duplicate in forbidden:
        next_duplicate = os.dup(fd)
        os.close(duplicate)
        duplicate = next_duplicate
    return duplicate


def _restore_frame_fds(
    targets: Sequence[int],
    saved: dict[int, int],
) -> None:
    for target in targets:
        try:
            os.close(target)
        except OSError:
            pass
        original = saved.pop(target, None)
        if original is not None:
            try:
                os.dup2(original, target)
            finally:
                os.close(original)


def _reserve_frame_fds(targets: Sequence[int]) -> dict[int, int]:
    """Keep command descriptor numbers free while creating anonymous pipes."""
    target_set = set(targets)
    saved: dict[int, int] = {}
    try:
        for target in targets:
            if _frame_fd_is_open(target):
                saved[target] = _duplicate_away(target, target_set)
                os.close(target)
        for target in targets:
            placeholder = os.open(os.devnull, os.O_RDONLY)
            if placeholder != target:
                os.dup2(placeholder, target)
                os.close(placeholder)
        return saved
    except Exception:
        _restore_frame_fds(targets, saved)
        raise


def _terminate_process(process: Any) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        process.kill()
    except OSError:
        pass
    try:
        process.wait(timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _close_frame_clients(
    clients: Sequence[object],
    feeders: Sequence[FrameFeeder],
) -> None:
    seen: set[int] = set()
    resources: list[object] = list(clients)
    resources.extend(getattr(feeder, "client", None) for feeder in feeders)
    for resource in resources:
        if resource is None or id(resource) in seen:
            continue
        seen.add(id(resource))
        close = getattr(resource, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass


def _run_pipe_with_frame_feeders(
    cmds: PipeCommands,
    *,
    timeout_s: float,
    frame_clients: Sequence[object],
    supplied_feeders: Sequence[FrameFeeder],
    active_feeders: list[FrameFeeder],
) -> PipeResult:
    """Run the audio/video pipe and optional same-pass frame feeders."""
    import tempfile

    overall_t0 = time.monotonic()
    audio_t0 = time.monotonic()
    if not cmds.melt_audio_cmd:
        # Audio was satisfied from the wav cache (orchestrator) — skip the
        # melt-audio pass entirely and mux the cached mix below.
        audio_rc = 0
        audio_err = ""
        audio_elapsed = 0.0
    else:
        try:
            audio_proc = subprocess.run(
                cmds.melt_audio_cmd,
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired:
            raise PipeRunError(f"melt-audio timed out after {timeout_s:g}s") from None
        audio_rc = audio_proc.returncode
        audio_err = audio_proc.stderr or ""
        if audio_rc != 0:
            return PipeResult(
                audio_rc,
                audio_rc,
                -1,
                f"melt-audio failed:\n{audio_err.strip()}",
                elapsed_sec=time.monotonic() - overall_t0,
                audio_elapsed_sec=time.monotonic() - audio_t0,
            )
        audio_elapsed = time.monotonic() - audio_t0

    frame_overlays = list(cmds.frame_overlays)
    if frame_overlays and os.name != "posix":
        raise PipeRunError("same-pass frame feeding requires POSIX inherited descriptors")
    if frame_overlays:
        if supplied_feeders:
            if len(supplied_feeders) != len(frame_overlays):
                raise PipeRunError("frame feeder count does not match frame overlay count")
            feeders = list(supplied_feeders)
        else:
            if len(frame_clients) != len(frame_overlays):
                raise PipeRunError("frame client count does not match frame overlay count")
            feeders = [
                FrameFeeder(client, overlay)
                for client, overlay in zip(frame_clients, frame_overlays)
            ]
        active_feeders.extend(feeders)
        frame_pipe_fds = tuple(cmds.frame_pipe_fds)
        if not frame_pipe_fds:
            frame_pipe_fds = tuple(
                overlay.pipe_fd
                for overlay in frame_overlays
                if overlay.pipe_fd is not None
            )
        if len(frame_pipe_fds) != len(frame_overlays) or any(
            fd is None or fd < 3 for fd in frame_pipe_fds
        ):
            raise PipeRunError("frame overlay descriptors are incomplete")
        if len(set(frame_pipe_fds)) != len(frame_pipe_fds):
            raise PipeRunError("frame overlay descriptors must be unique")
    else:
        feeders = []
        frame_pipe_fds = ()

    deadline = time.monotonic() + timeout_s
    with tempfile.TemporaryFile() as melt_err_f, tempfile.TemporaryFile() as ff_err_f:
        melt = None
        ffmpeg = None
        frame_pipes: list[tuple[int, int]] = []
        saved_frame_fds: dict[int, int] = {}
        frame_fds_reserved = False
        frame_fds_restored = False
        feeder_errors: list[str] = []
        feeder_threads: list[threading.Thread] = []
        melt_failed_early = False
        try:
            if frame_pipe_fds:
                saved_frame_fds = _reserve_frame_fds(frame_pipe_fds)
                frame_fds_reserved = True
                frame_pipes = [os.pipe() for _fd in frame_pipe_fds]
                for target, (read_fd, _write_fd) in zip(
                    frame_pipe_fds,
                    frame_pipes,
                ):
                    os.dup2(read_fd, target)
                    os.set_inheritable(target, True)
                    os.close(read_fd)
            melt = subprocess.Popen(
                cmds.melt_video_cmd,
                stdout=subprocess.PIPE,
                stderr=melt_err_f,
            )
            ffmpeg_kwargs: dict[str, object] = {
                "stdin": melt.stdout,
                "stderr": ff_err_f,
            }
            if frame_pipe_fds:
                ffmpeg_kwargs["pass_fds"] = tuple(frame_pipe_fds)
            ffmpeg = subprocess.Popen(cmds.ffmpeg_cmd, **ffmpeg_kwargs)
        except OSError as exc:
            _terminate_process(melt)
            _terminate_process(ffmpeg)
            for read_fd, write_fd in frame_pipes:
                for fd in (read_fd, write_fd):
                    try:
                        os.close(fd)
                    except OSError:
                        pass
            raise PipeRunError(f"pipe spawn failed: {exc}") from None
        finally:
            if frame_fds_reserved and not frame_fds_restored:
                _restore_frame_fds(frame_pipe_fds, saved_frame_fds)
                frame_fds_restored = True

        assert melt is not None
        assert ffmpeg is not None
        assert melt.stdout is not None
        melt.stdout.close()

        def _feed(feeder: FrameFeeder, write_fd: int) -> None:
            try:
                with os.fdopen(write_fd, "wb", buffering=0) as output:
                    feeder.write_frames(output, output_fps=feeder.overlay.fps)
            except FrameFeederError as exc:
                feeder_errors.append(exc.detail)
            except (BrokenPipeError, OSError) as exc:
                feeder_errors.append(str(exc)[:512])
            except Exception as exc:
                feeder_errors.append(str(exc)[:512])

        if feeders:
            for index, (feeder, (_read_fd, write_fd)) in enumerate(
                zip(feeders, frame_pipes)
            ):
                thread = threading.Thread(
                    target=_feed,
                    args=(feeder, write_fd),
                    name=f"open-edit-frame-feeder-{index}",
                    daemon=True,
                )
                feeder_threads.append(thread)
                thread.start()

        ffmpeg_wait_t0 = time.monotonic()
        try:
            while ffmpeg.poll() is None:
                if feeder_errors:
                    _terminate_process(melt)
                    _terminate_process(ffmpeg)
                    raise PipeRunError(
                        f"frame feeder failed: {feeder_errors[0][:512]}"
                    )
                if melt.poll() is not None and melt.returncode != 0:
                    melt_failed_early = True
                    _terminate_process(ffmpeg)
                    break
                if time.monotonic() >= deadline:
                    _terminate_process(melt)
                    _terminate_process(ffmpeg)
                    raise PipeRunError(
                        f"render pipe timed out after {timeout_s:g}s"
                    )
                time.sleep(0.01)
            ffmpeg_rc = ffmpeg.wait(timeout=2)
        except subprocess.TimeoutExpired:
            _terminate_process(melt)
            _terminate_process(ffmpeg)
            raise PipeRunError(f"render pipe timed out after {timeout_s:g}s") from None
        finally:
            for feeder in feeders:
                feeder.stop()
            for thread in feeder_threads:
                thread.join(timeout=2)
            for read_fd, write_fd in frame_pipes:
                for fd in (read_fd, write_fd):
                    try:
                        os.close(fd)
                    except OSError:
                        pass

        if feeder_errors:
            _terminate_process(melt)
            raise PipeRunError(f"frame feeder failed: {feeder_errors[0][:512]}")
        ffmpeg_elapsed = time.monotonic() - ffmpeg_wait_t0
        melt_wait_t0 = time.monotonic()
        try:
            melt_rc = melt.wait(timeout=30)
        except subprocess.TimeoutExpired:
            _terminate_process(melt)
            melt_rc = melt.wait()
        melt_elapsed = time.monotonic() - melt_wait_t0
        melt_err_f.seek(0)
        ff_err_f.seek(0)
        melt_err = melt_err_f.read().decode("utf-8", errors="replace").strip()
        ff_err = ff_err_f.read().decode("utf-8", errors="replace").strip()

    stderr = "\n".join(
        part
        for part in (
            f"melt (rc={melt_rc}): {melt_err[-400:]}" if melt_err else "",
            f"ffmpeg (rc={ffmpeg_rc}): {ff_err[-400:]}" if ff_err else "",
        )
        if part
    )
    frame_count = sum(feeder.frames_requested for feeder in feeders)
    frame_elapsed = max(
        (feeder.elapsed_sec for feeder in feeders),
        default=0.0,
    )
    if ffmpeg_rc != 0 and not melt_failed_early:
        return PipeResult(
            ffmpeg_rc,
            melt_rc,
            ffmpeg_rc,
            stderr,
            elapsed_sec=time.monotonic() - overall_t0,
            audio_elapsed_sec=audio_elapsed,
            melt_elapsed_sec=melt_elapsed,
            ffmpeg_elapsed_sec=ffmpeg_elapsed,
            frames_requested=frame_count,
            frame_elapsed_sec=frame_elapsed,
        )
    if melt_rc != 0:
        return PipeResult(
            melt_rc,
            melt_rc,
            ffmpeg_rc,
            stderr,
            elapsed_sec=time.monotonic() - overall_t0,
            audio_elapsed_sec=audio_elapsed,
            melt_elapsed_sec=melt_elapsed,
            ffmpeg_elapsed_sec=ffmpeg_elapsed,
            frames_requested=frame_count,
            frame_elapsed_sec=frame_elapsed,
        )
    return PipeResult(
        0,
        0,
        0,
        stderr,
        elapsed_sec=time.monotonic() - overall_t0,
        audio_elapsed_sec=audio_elapsed,
        melt_elapsed_sec=melt_elapsed,
        ffmpeg_elapsed_sec=ffmpeg_elapsed,
        frames_requested=frame_count,
        frame_elapsed_sec=frame_elapsed,
    )


def run_pipe(
    cmds: PipeCommands,
    *,
    timeout_s: float,
    frame_clients: Sequence[object] = (),
    frame_feeders: Sequence[FrameFeeder] = (),
) -> PipeResult:
    """Run melt, ffmpeg, and optional same-pass Remotion frame feeders."""
    clients = list(frame_clients)
    active_feeders: list[FrameFeeder] = list(frame_feeders)
    try:
        return _run_pipe_with_frame_feeders(
            cmds,
            timeout_s=timeout_s,
            frame_clients=clients,
            supplied_feeders=frame_feeders,
            active_feeders=active_feeders,
        )
    finally:
        for feeder in active_feeders:
            feeder.stop()
        _close_frame_clients(clients, active_feeders)
