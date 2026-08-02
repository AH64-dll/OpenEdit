"""Host-only Remotion frame-pull protocol.

The frame engine deliberately owns only a small binary framing contract.  It
does not materialize media, write to the CAS, or expose a network listener.
The normal render path remains materialization until a later feeder task
explicitly enables frame pull.
"""
from __future__ import annotations

import json
import math
import os
import queue
import re
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping, Sequence

REMOTION_VERSION = "4.0.278"
DEFAULT_MAX_PROPS_JSON_BYTES = 1_000_000
DEFAULT_MAX_RESPONSE_BYTES = 64 * 1024 * 1024
MAX_FRAME_DIMENSION = 8192
MAX_FPS = 240.0
MAX_HEADER_BYTES = 64 * 1024
MAX_ERROR_BYTES = 512
FRAME_SERVER_PATH = Path(__file__).resolve().parent.parent / "remotion_frame_server.mjs"

FrameEngine = Literal["materialize", "pull"]


class FrameProtocolError(RuntimeError):
    """Raised when a frame request or response violates the protocol."""


class FramePullUnavailableError(FrameProtocolError):
    """Raised when the experimental pull engine is requested too early."""

    code = "remotion_frame_pull_unavailable"
    error_code = code

    def __init__(self, detail: str = "same-pass frame feeding is not enabled") -> None:
        super().__init__(f"{self.code}: {detail}")

    def as_dict(self) -> dict[str, str]:
        return {"ok": False, "error_code": self.code, "error": str(self)}


def _bounded_text(value: object, *, limit: int = MAX_ERROR_BYTES) -> str:
    text = str(value).replace("\x00", " ").strip()
    return text[:limit] or "unknown frame server error"


def _json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise FrameProtocolError(f"props are not JSON serializable: {exc}") from exc


def _validate_relative_entry_point(entry_point: str) -> None:
    if not isinstance(entry_point, str) or not entry_point:
        raise FrameProtocolError("entry_point must be a non-empty relative path")
    if "\x00" in entry_point:
        raise FrameProtocolError("entry_point contains a NUL byte")
    if entry_point.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:[\\/]", entry_point):
        raise FrameProtocolError(
            "entry_point must be relative under .open_edit/remotion"
        )
    parts = entry_point.replace("\\", "/").split("/")
    if any(part == ".." for part in parts):
        raise FrameProtocolError(
            "entry_point must stay under .open_edit/remotion; parent traversal is forbidden"
        )


@dataclass(frozen=True)
class FrameRequest:
    """A single frame request sent as one JSON line."""

    request_id: str
    composition_id: str
    entry_point: str
    props: dict[str, object]
    frame: int
    width: int
    height: int
    fps: float
    alpha: bool
    remotion_version: str = REMOTION_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.request_id, str) or not self.request_id.strip():
            raise FrameProtocolError("request_id must be a non-empty string")
        if len(self.request_id) > 256 or "\n" in self.request_id or "\r" in self.request_id:
            raise FrameProtocolError("request_id is too long or contains a newline")
        if not isinstance(self.composition_id, str) or not self.composition_id.strip():
            raise FrameProtocolError("composition_id must be a non-empty string")
        if len(self.composition_id) > 256:
            raise FrameProtocolError("composition_id is too long")

        # Validate frame before the path so a request containing both errors
        # reports the most directly bounded numeric violation.
        if isinstance(self.frame, bool) or not isinstance(self.frame, int) or self.frame < 0:
            raise FrameProtocolError("frame must be a non-negative integer")
        for name, value in (("width", self.width), ("height", self.height)):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise FrameProtocolError(f"{name} must be a positive integer")
            if value > MAX_FRAME_DIMENSION:
                raise FrameProtocolError(
                    f"{name} exceeds maximum frame dimension {MAX_FRAME_DIMENSION}"
                )
        if isinstance(self.fps, bool) or not isinstance(self.fps, (int, float)):
            raise FrameProtocolError("fps must be a positive finite number")
        if not math.isfinite(float(self.fps)) or float(self.fps) <= 0:
            raise FrameProtocolError("fps must be a positive finite number")
        if float(self.fps) > MAX_FPS:
            raise FrameProtocolError(f"fps exceeds maximum {MAX_FPS:g}")
        if not isinstance(self.props, dict):
            raise FrameProtocolError("props must be a JSON object")
        if not isinstance(self.alpha, bool):
            raise FrameProtocolError("alpha must be a boolean")
        if self.remotion_version != REMOTION_VERSION:
            raise FrameProtocolError(
                f"unsupported Remotion version {self.remotion_version!r}; "
                f"expected {REMOTION_VERSION}"
            )
        _validate_relative_entry_point(self.entry_point)
        _json_bytes(self.props)

    def to_dict(self) -> dict[str, object]:
        return {
            "request_id": self.request_id,
            "composition_id": self.composition_id,
            "entry_point": self.entry_point,
            "props": self.props,
            "frame": self.frame,
            "width": self.width,
            "height": self.height,
            "fps": float(self.fps),
            "alpha": self.alpha,
            "remotion_version": self.remotion_version,
        }


@dataclass(frozen=True)
class FrameResponse:
    """The validated PNG frame returned by the private server."""

    request_id: str
    content_type: str
    bytes: bytes
    width: int
    height: int
    frame: int
    remotion_version: str

    @property
    def payload(self) -> bytes:
        """Alias useful to callers that avoid the ``bytes`` field name."""
        return self.bytes


FrameResult = FrameResponse


def frame_engine_mode(requested: str | None = None) -> FrameEngine:
    """Read the opt-in selector without enabling the experimental feeder."""
    raw = (
        requested
        if requested is not None
        else os.environ.get("OPEN_EDIT_REMOTION_FRAME_ENGINE", "materialize")
    )
    mode = str(raw).strip().lower()
    if mode not in {"materialize", "pull"}:
        raise FrameProtocolError(
            "OPEN_EDIT_REMOTION_FRAME_ENGINE must be materialize or pull"
        )
    return mode  # type: ignore[return-value]


def select_frame_engine(
    requested: str | None = None,
    *,
    allow_pull: bool = False,
) -> FrameEngine:
    """Resolve the engine gate while preserving materialize as the default.

    ``allow_pull`` is intentionally explicit.  Task 8 proves the protocol,
    while the same-pass feeder that can enable it belongs to a later task.
    """
    mode = frame_engine_mode(requested)
    if mode == "pull" and not allow_pull:
        raise FramePullUnavailableError()
    return mode


resolve_frame_engine = select_frame_engine


def frame_engine_status(
    requested: str | None = None,
    *,
    allow_pull: bool = False,
) -> dict[str, object]:
    """Return a JSON-compatible selector result for job-layer callers."""
    try:
        mode = select_frame_engine(requested, allow_pull=allow_pull)
    except FramePullUnavailableError as exc:
        return exc.as_dict()
    return {"ok": True, "engine": mode}


def build_frame_server_command(
    project_path: Path,
    *,
    node_bin: str | None = None,
    server_path: Path = FRAME_SERVER_PATH,
    request_timeout_s: float | None = None,
) -> list[str]:
    """Build a non-shell command for one project-local frame server."""
    project_root = Path(project_path).resolve()
    program = node_bin or os.environ.get("OPEN_EDIT_NODE_BIN", "node")
    command = [
        program,
        str(Path(server_path).resolve()),
        "--project-root",
        str(project_root),
    ]
    if request_timeout_s is not None:
        if not math.isfinite(request_timeout_s) or request_timeout_s <= 0:
            raise FrameProtocolError("request_timeout_s must be positive and finite")
        command.extend(["--request-timeout-ms", str(int(request_timeout_s * 1000))])
    return command


class FramePullClient:
    """Talk to one private stdin/stdout Remotion frame server process."""

    def __init__(
        self,
        command: Sequence[str],
        *,
        timeout_s: float = 30.0,
        max_props_json_bytes: int = DEFAULT_MAX_PROPS_JSON_BYTES,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        max_props_bytes: int | None = None,
        cwd: str | Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        if not command or any(not isinstance(part, str) or not part for part in command):
            raise FrameProtocolError("frame server command must be a non-empty argv")
        if not math.isfinite(timeout_s) or timeout_s <= 0:
            raise FrameProtocolError("timeout_s must be positive and finite")
        if max_props_bytes is not None:
            max_props_json_bytes = max_props_bytes
        if max_props_json_bytes <= 0:
            raise FrameProtocolError("max_props_json_bytes must be positive")
        if max_response_bytes <= 0:
            raise FrameProtocolError("max_response_bytes must be positive")

        self.command = tuple(command)
        self.timeout_s = float(timeout_s)
        self.max_props_json_bytes = int(max_props_json_bytes)
        self.max_response_bytes = int(max_response_bytes)
        self.cwd = str(cwd) if cwd is not None else None
        self.env = dict(env) if env is not None else None
        self._process: subprocess.Popen[bytes] | None = None
        self._stdout_queue: queue.Queue[bytes | None] | None = None
        self._stdout_buffer = bytearray()
        self._reader: threading.Thread | None = None
        self._closed = False
        self._broken = False

    @classmethod
    def for_project(
        cls,
        project_path: Path,
        *,
        node_bin: str | None = None,
        timeout_s: float = 30.0,
        max_props_json_bytes: int = DEFAULT_MAX_PROPS_JSON_BYTES,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        request_timeout_s: float | None = None,
    ) -> "FramePullClient":
        return cls(
            build_frame_server_command(
                project_path,
                node_bin=node_bin,
                request_timeout_s=request_timeout_s,
            ),
            timeout_s=timeout_s,
            max_props_json_bytes=max_props_json_bytes,
            max_response_bytes=max_response_bytes,
        )

    from_project = for_project

    def request_frame(self, request: FrameRequest) -> FrameResponse:
        if not isinstance(request, FrameRequest):
            raise FrameProtocolError("request_frame expects a FrameRequest")
        props_size = len(_json_bytes(request.props))
        if props_size > self.max_props_json_bytes:
            raise FrameProtocolError(
                f"props JSON is {props_size} bytes; maximum is "
                f"{self.max_props_json_bytes} bytes"
            )

        self._ensure_process()
        process = self._process
        assert process is not None
        request_line = _json_bytes(request.to_dict()) + b"\n"
        deadline = time.monotonic() + self.timeout_s
        try:
            assert process.stdin is not None
            process.stdin.write(request_line)
            process.stdin.flush()
            header_line = self._read_line(deadline)
            header = self._decode_header(header_line)
            if header.get("request_id") != request.request_id:
                raise FrameProtocolError(
                    "frame response request_id does not match the request"
                )
            if header.get("ok") is not True:
                error = _bounded_text(header.get("error", "frame server rejected request"))
                raise _FrameServerReportedError(error)

            self._validate_success_header(header, request)
            byte_length = header["byte_length"]
            payload = self._read_exact(byte_length, deadline)
            if len(payload) != byte_length:
                raise FrameProtocolError(
                    f"frame payload length mismatch: expected {byte_length}, got {len(payload)}"
                )
            self._check_nonzero_exit(process)
            return FrameResponse(
                request_id=request.request_id,
                content_type="image/png",
                bytes=payload,
                width=header["width"],
                height=header["height"],
                frame=header["frame"],
                remotion_version=header["remotion_version"],
            )
        except _FrameServerReportedError:
            # A bounded, structured render error does not corrupt framing, so
            # the long-lived private process may serve another request.
            raise
        except (BrokenPipeError, OSError) as exc:
            self._invalidate()
            raise FrameProtocolError(f"frame server I/O failed: {_bounded_text(exc)}") from exc
        except FrameProtocolError:
            self._invalidate()
            raise

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        process = self._process
        self._process = None
        if process is None:
            return
        try:
            if process.stdin is not None:
                process.stdin.close()
        except OSError:
            pass
        try:
            process.wait(timeout=min(max(self.timeout_s, 0.1), 2.0))
        except subprocess.TimeoutExpired:
            self._terminate(process)
        finally:
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except OSError:
                        pass

    def __enter__(self) -> "FramePullClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _ensure_process(self) -> None:
        if self._closed:
            raise FrameProtocolError("frame client is closed")
        if self._broken:
            raise FrameProtocolError("frame client is unusable after a protocol failure")
        if self._process is not None:
            if self._process.poll() is not None:
                self._invalidate()
                raise FrameProtocolError("frame server exited before the next request")
            return
        try:
            process = subprocess.Popen(
                self.command,
                cwd=self.cwd,
                env=self.env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=0,
                start_new_session=(os.name == "posix"),
            )
        except OSError as exc:
            self._broken = True
            raise FrameProtocolError(
                f"could not start frame server: {_bounded_text(exc)}"
            ) from exc
        self._process = process
        assert process.stdout is not None
        self._stdout_queue = queue.Queue()
        self._stdout_buffer.clear()

        def pump_stdout() -> None:
            try:
                while True:
                    chunk = os.read(process.stdout.fileno(), 64 * 1024)
                    if not chunk:
                        break
                    assert self._stdout_queue is not None
                    self._stdout_queue.put(chunk)
            except (OSError, ValueError):
                pass
            finally:
                if self._stdout_queue is not None:
                    self._stdout_queue.put(None)

        self._reader = threading.Thread(
            target=pump_stdout,
            name="open-edit-frame-server-stdout",
            daemon=True,
        )
        self._reader.start()

    def _read_line(self, deadline: float) -> bytes:
        while True:
            newline = self._stdout_buffer.find(b"\n")
            if newline >= 0:
                line = bytes(self._stdout_buffer[:newline])
                del self._stdout_buffer[: newline + 1]
                if len(line) > MAX_HEADER_BYTES:
                    raise FrameProtocolError("frame response header is too large")
                return line
            if len(self._stdout_buffer) > MAX_HEADER_BYTES:
                raise FrameProtocolError("frame response header is too large")
            self._read_chunk(deadline)

    def _read_exact(self, length: int, deadline: float) -> bytes:
        while len(self._stdout_buffer) < length:
            self._read_chunk(deadline)
        payload = bytes(self._stdout_buffer[:length])
        del self._stdout_buffer[:length]
        return payload

    def _read_chunk(self, deadline: float) -> None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise FrameProtocolError(
                f"frame response timed out after {self.timeout_s:.3f}s"
            )
        if self._stdout_queue is None:
            raise FrameProtocolError("frame server stdout is unavailable")
        try:
            chunk = self._stdout_queue.get(timeout=remaining)
        except queue.Empty as exc:
            raise FrameProtocolError(
                f"frame response timed out after {self.timeout_s:.3f}s"
            ) from exc
        if chunk is None:
            process = self._process
            rc = process.poll() if process is not None else None
            if rc is not None and rc != 0:
                raise FrameProtocolError(f"frame server exited with status {rc}")
            raise FrameProtocolError("frame server closed stdout before the response")
        self._stdout_buffer.extend(chunk)

    @staticmethod
    def _decode_header(raw: bytes) -> dict[str, object]:
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FrameProtocolError("frame response header is not valid JSON") from exc
        if not isinstance(value, dict):
            raise FrameProtocolError("frame response header must be a JSON object")
        return value

    def _validate_success_header(
        self,
        header: dict[str, object],
        request: FrameRequest,
    ) -> None:
        if header.get("content_type") != "image/png":
            raise FrameProtocolError("frame response content_type must be image/png")
        version = header.get("remotion_version")
        if version != request.remotion_version:
            raise FrameProtocolError("frame response Remotion version does not match")
        for name in ("width", "height", "frame", "byte_length"):
            value = header.get(name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise FrameProtocolError(f"frame response {name} must be an integer")
        if header["width"] != request.width or header["height"] != request.height:
            raise FrameProtocolError("frame response dimensions do not match request")
        if header["frame"] != request.frame:
            raise FrameProtocolError("frame response frame does not match request")
        byte_length = header["byte_length"]
        if byte_length <= 0:
            raise FrameProtocolError("frame response byte_length must be positive")
        if byte_length > self.max_response_bytes:
            raise FrameProtocolError(
                f"frame response exceeds maximum {self.max_response_bytes} bytes"
            )

    def _check_nonzero_exit(self, process: subprocess.Popen[bytes]) -> None:
        rc = process.poll()
        if rc is not None and rc != 0:
            raise FrameProtocolError(f"frame server exited with status {rc}")

    def _invalidate(self) -> None:
        self._broken = True
        process = self._process
        self._process = None
        if process is not None:
            self._terminate(process)

    @staticmethod
    def _terminate(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
            process.wait(timeout=1.0)
            return
        except (OSError, ProcessLookupError, subprocess.TimeoutExpired):
            pass
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            process.wait(timeout=1.0)
        except (OSError, ProcessLookupError, subprocess.TimeoutExpired):
            pass


class _FrameServerReportedError(FrameProtocolError):
    """Internal marker for a valid ``ok=false`` response."""
