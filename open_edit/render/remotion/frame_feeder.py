"""Incremental Remotion PNG feeding for the experimental ffmpeg pipe path.

The feeder owns no media cache and never renders ahead of the requested frame.
Each instance consumes one :class:`FramePullClient` and writes one bounded
composition's PNG sequence to a non-seekable output.
"""
from __future__ import annotations

import math
import os
import shutil
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO

from open_edit.render.remotion.frame_engine import (
    FRAME_SERVER_PATH,
    FramePullClient,
    FrameRequest,
)

MAX_FEEDER_ERROR_BYTES = 512


def _bounded_error(value: object) -> str:
    return str(value).replace("\x00", " ").replace("\r", " ").replace("\n", " ")[:MAX_FEEDER_ERROR_BYTES]


@dataclass(frozen=True)
class FrameOverlaySpec:
    """The composition metadata needed to request a frame sequence."""

    composition_uid: str
    composition_id: str
    entry_point: str
    props: dict[str, Any]
    position_sec: float
    duration_sec: float
    width: int
    height: int
    fps: float
    alpha: bool
    blur_under: bool = False
    # Assigned by ``build_pipe_commands`` for the Linux inherited pipe.
    pipe_fd: int | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("composition_uid", self.composition_uid),
            ("composition_id", self.composition_id),
            ("entry_point", self.entry_point),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if len(self.composition_uid) > 220:
            raise ValueError("composition_uid is too long")
        if isinstance(self.props, Mapping):
            object.__setattr__(self, "props", dict(self.props))
        else:
            raise TypeError("props must be a mapping")
        if (
            not isinstance(self.position_sec, (int, float))
            or not math.isfinite(float(self.position_sec))
            or float(self.position_sec) < 0
        ):
            raise ValueError("position_sec must be finite and non-negative")
        if (
            not isinstance(self.duration_sec, (int, float))
            or not math.isfinite(float(self.duration_sec))
            or float(self.duration_sec) <= 0
        ):
            raise ValueError("duration_sec must be finite and positive")
        for name, value in (("width", self.width), ("height", self.height)):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if (
            isinstance(self.fps, bool)
            or not isinstance(self.fps, (int, float))
            or not math.isfinite(float(self.fps))
            or float(self.fps) <= 0
        ):
            raise ValueError("fps must be a positive finite number")
        if not isinstance(self.alpha, bool):
            raise TypeError("alpha must be a boolean")
        if not isinstance(self.blur_under, bool):
            raise TypeError("blur_under must be a boolean")
        if self.pipe_fd is not None and (
            isinstance(self.pipe_fd, bool)
            or not isinstance(self.pipe_fd, int)
            or self.pipe_fd < 3
        ):
            raise ValueError("pipe_fd must be an inherited descriptor number")

    @property
    def frame_count(self) -> int:
        """Number of source frames needed to cover this composition."""
        return max(1, math.ceil(float(self.duration_sec) * float(self.fps)))

    def request(self, frame: int) -> FrameRequest:
        """Build the protocol request for one monotonic source frame."""
        return FrameRequest(
            request_id=f"{self.composition_uid}:{frame}",
            composition_id=self.composition_id,
            entry_point=self.entry_point,
            props=dict(self.props),
            frame=frame,
            width=self.width,
            height=self.height,
            fps=float(self.fps),
            alpha=self.alpha,
        )


class FrameFeederError(RuntimeError):
    """Raised when a frame cannot be requested or written to ffmpeg."""

    code = "remotion_frame_pull_failed"

    def __init__(self, detail: str) -> None:
        self.detail = _bounded_error(detail)
        super().__init__(f"{self.code}: {self.detail}")


@dataclass
class FrameFeeder:
    """Synchronously request and stream one composition's PNG frames."""

    client: Any
    overlay: FrameOverlaySpec
    _stop_event: threading.Event = field(
        default_factory=threading.Event,
        init=False,
        repr=False,
    )
    frames_requested: int = field(default=0, init=False)
    elapsed_sec: float = field(default=0.0, init=False)
    error: str | None = field(default=None, init=False)

    def stop(self) -> None:
        """Stop after the current protocol request and let the pipe close."""
        self._stop_event.set()

    def write_frames(
        self,
        output: BinaryIO,
        output_fps: float | None = None,
    ) -> int:
        """Write PNG frames in source-frame order and return the count.

        ``output_fps`` is accepted so the runner can validate the ffmpeg input
        contract. Source requests intentionally remain at the composition FPS:
        ffmpeg's filter graph owns the timeline offset and presentation timing.
        """
        if output_fps is not None and (
            isinstance(output_fps, bool)
            or not isinstance(output_fps, (int, float))
            or not math.isfinite(float(output_fps))
            or float(output_fps) <= 0
        ):
            raise ValueError("output_fps must be a positive finite number")

        started = time.monotonic()
        try:
            for frame in range(self.overlay.frame_count):
                if self._stop_event.is_set():
                    break
                request = self.overlay.request(frame)
                try:
                    response = self.client.request_frame(request)
                    payload = getattr(response, "payload", None)
                    if payload is None:
                        payload = getattr(response, "bytes", response)
                    if not isinstance(payload, (bytes, bytearray, memoryview)):
                        raise TypeError("frame response did not contain image bytes")
                    if not payload:
                        raise ValueError("frame response contained no image bytes")
                    output.write(bytes(payload))
                    flush = getattr(output, "flush", None)
                    if callable(flush):
                        flush()
                except Exception as exc:
                    raise FrameFeederError(_bounded_error(exc)) from exc
                self.frames_requested += 1
            return self.frames_requested
        except FrameFeederError as exc:
            self.error = exc.detail
            raise
        finally:
            self.elapsed_sec = time.monotonic() - started


def frame_pull_platform_supported() -> bool:
    """Return whether inherited read descriptors are available on this host."""
    return os.name == "posix" and hasattr(os, "pipe")


def probe_frame_pull_host(project_path: Path) -> tuple[bool, str | None]:
    """Perform the cheap host/protocol gate before starting a render.

    The actual Remotion API probe happens in the Task 8 server on the first
    request. This gate rejects unsupported process plumbing, a missing private
    server, an unavailable Node binary, or a missing project Remotion root
    without changing the materialize default.
    """
    if not frame_pull_platform_supported():
        return False, "inherited frame descriptors are unavailable on this platform"
    if not FRAME_SERVER_PATH.is_file():
        return False, "Remotion frame server is unavailable"
    node_bin = os.environ.get("OPEN_EDIT_NODE_BIN", "node")
    if shutil.which(node_bin) is None:
        return False, "Node.js is unavailable for the Remotion frame server"
    remotion_root = Path(project_path) / ".open_edit" / "remotion"
    if not remotion_root.is_dir():
        return False, "project Remotion root is unavailable"
    return True, None


def build_frame_pull_clients(
    project_path: Path,
    overlays: list[FrameOverlaySpec],
    *,
    timeout_s: float = 30.0,
) -> list[FramePullClient]:
    """Create one private protocol client per concurrent feeder."""
    return [
        FramePullClient.for_project(project_path, timeout_s=timeout_s)
        for _overlay in overlays
    ]


__all__ = [
    "FrameFeeder",
    "FrameFeederError",
    "FrameOverlaySpec",
    "build_frame_pull_clients",
    "frame_pull_platform_supported",
    "probe_frame_pull_host",
]
