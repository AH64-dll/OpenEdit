"""Schema and status helpers for chunked timeline previews."""
from __future__ import annotations

import math
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

PreviewStatus = Literal["red", "yellow", "green"]
PreviewMedia = Literal["video", "audio", "both"]


class PreviewRange(BaseModel):
    """A requested timeline range in project seconds."""

    start_sec: float = Field(ge=0)
    end_sec: float = Field(gt=0)

    @field_validator("start_sec", "end_sec")
    @classmethod
    def _finite_seconds(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("preview range seconds must be finite")
        return value

    @model_validator(mode="after")
    def _end_after_start(self) -> PreviewRange:
        if self.end_sec <= self.start_sec:
            raise ValueError("end_sec must be greater than start_sec")
        return self


class PreviewArtifact(BaseModel):
    """A validated artifact stored below the preview cache root."""

    artifact_id: str
    relative_path: str
    mime: str
    bytes: int = Field(ge=1)
    sha256: str
    graph_hash: str
    key: str

    @field_validator("relative_path")
    @classmethod
    def _relative_path_only(cls, value: str) -> str:
        if not value or "\x00" in value:
            raise ValueError("relative_path must be a non-empty relative path")
        if "\\" in value:
            raise ValueError("relative_path must use POSIX separators")

        posix_path = PurePosixPath(value)
        windows_path = PureWindowsPath(value)
        if (
            posix_path.is_absolute()
            or windows_path.is_absolute()
            or bool(windows_path.drive)
            or any(part == ".." for part in posix_path.parts)
        ):
            raise ValueError("relative_path must not be absolute or escape its root")
        return value


class PreviewPlaneState(BaseModel):
    """Current and same-range fallback state for one preview plane."""

    status: PreviewStatus
    current: PreviewArtifact | None = None
    fallback: PreviewArtifact | None = None


class PreviewChunk(BaseModel):
    """One frame-aligned core chunk and its independent artifact states."""

    chunk_id: str
    index: int = Field(ge=0)
    start_frame: int = Field(ge=0)
    end_frame: int = Field(gt=0)
    start_sec: float = Field(ge=0)
    end_sec: float = Field(gt=0)
    status: PreviewStatus
    video: PreviewPlaneState
    audio: PreviewPlaneState
    playback: PreviewPlaneState

    @field_validator("start_sec", "end_sec")
    @classmethod
    def _finite_seconds(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("chunk seconds must be finite")
        return value

    @model_validator(mode="after")
    def _monotonic_bounds(self) -> PreviewChunk:
        if self.end_frame <= self.start_frame:
            raise ValueError("end_frame must be greater than start_frame")
        if self.end_sec <= self.start_sec:
            raise ValueError("end_sec must be greater than start_sec")
        return self


class PreviewManifest(BaseModel):
    """The atomically published schema-versioned preview manifest."""

    schema_version: Literal[1] = 1
    project_id: str
    graph_revision: int = Field(ge=0)
    edit_graph_hash: str
    duration_frames: int = Field(ge=0)
    duration_sec: float = Field(ge=0)
    fps_num: int = Field(gt=0)
    fps_den: int = Field(gt=0)
    chunk_frames: int = Field(gt=0)
    profile: dict[str, Any]
    job_id: str | None = None
    updated_at: float
    chunks: list[PreviewChunk]

    @field_validator("duration_sec", "updated_at")
    @classmethod
    def _finite_manifest_seconds(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("manifest floating-point values must be finite")
        return value


def _has_playable_artifact(state: PreviewPlaneState) -> bool:
    """Return whether a state exposes a current or fallback playable artifact."""

    if state.status == "green":
        return state.current is not None
    return state.fallback is not None


def _is_current(state: PreviewPlaneState) -> bool:
    return state.status == "green" and state.current is not None


def effective_status(chunk: PreviewChunk) -> PreviewStatus:
    """Derive the status visible to a preview consumer.

    Green requires a current artifact for every plane.  A dirty/red plane can
    still make the chunk yellow when any plane exposes a validated same-range
    fallback (or another playable current artifact).  With no playable
    current or fallback artifact, the chunk is red.
    """

    planes = (chunk.video, chunk.audio, chunk.playback)
    if chunk.status == "green" and all(_is_current(state) for state in planes):
        return "green"
    if any(_has_playable_artifact(state) for state in planes):
        return "yellow"
    return "red"


__all__ = [
    "PreviewArtifact",
    "PreviewChunk",
    "PreviewManifest",
    "PreviewMedia",
    "PreviewPlaneState",
    "PreviewRange",
    "PreviewStatus",
    "effective_status",
]
