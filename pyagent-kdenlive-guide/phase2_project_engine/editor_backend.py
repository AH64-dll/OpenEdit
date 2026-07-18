"""
editor_backend.py — abstract interface for PyAgent's "edit project" operations.

Phase 3 (the LLM tool-calling loop) calls operations on this interface,
NOT on file I/O directly. This is the load-bearing design decision
called out in 01_FINDINGS_AND_ARCHITECTURE.md §5.1: PyAgent's brain
shouldn't change if we swap the file-based backend for a D-Bus
backend (or any other). The contract is the contract.

Two implementations are planned:
  A. KdenliveFileBackend — reads/writes .kdenlive XML directly. Default
     for v1. Implemented in kdenlive_file_backend.py.
  B. KdenliveDBusBackend — calls into a running Kdenlive via D-Bus.
     Live edits, with Kdenlive's own undo stack. Optional/stretch.

The interface is intentionally small. Operations the user can express
("add a crossfade", "trim this clip", "color correct this clip") map
1:1 to backend methods. Compound operations ("swap these two clips
on the timeline") are composition: backend.move_clip(A) +
backend.move_clip(B).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Sequence


# ---- Plain-data return types (no XML, no D-Bus refs in the public API) ----


@dataclass(frozen=True)
class ProjectInfo:
    """Top-level project metadata. Returned by get_project_info()."""

    name: str
    fps: float
    width: int
    height: int
    colorspace: str
    track_count: int
    duration_sec: float
    path: str | None  # None for an in-memory project


@dataclass(frozen=True)
class ClipSummary:
    """A clip on the timeline. Returned by get_timeline_summary().

    `source_id` is the bin producer's `kdenlive:id` (e.g. "1", "21").
    This is the value to pass to append_clip/insert_clip/move_clip as
    `source_id` — NOT `clip_id` (which is the timeline-entry id).
    """

    clip_id: str
    track_index: int
    start_sec: float
    end_sec: float
    source_id: str
    source_path: str
    source_name: str
    source_in_sec: float
    source_out_sec: float
    effects: tuple[str, ...]


@dataclass(frozen=True)
class TransitionSummary:
    """A transition between two clips. Returned by get_timeline_summary()."""

    transition_id: str
    track_index: int
    start_sec: float
    end_sec: float
    kind: str  # "dissolve" | "fade" | "wipe" | ...


@dataclass(frozen=True)
class TimelineSummary:
    """Plain-data view of the timeline. Designed to render as a markdown
    table in Phase 3 (token efficiency per the findings doc)."""

    project: ProjectInfo
    tracks: tuple["TrackSummary", ...]
    clips: tuple[ClipSummary, ...]
    transitions: tuple[TransitionSummary, ...]
    markers: tuple["MarkerSummary", ...]


@dataclass(frozen=True)
class TrackSummary:
    index: int
    kind: str  # "video" | "audio"
    name: str
    clip_count: int


@dataclass(frozen=True)
class MarkerSummary:
    position_sec: float
    label: str
    kind: str  # "marker" | "guide" | "chapter"


# ---- Errors ----


class BackendError(Exception):
    """Base class for all backend errors. Phase 3 catches this and surfaces
    the message (which always contains a `fix:` hint per the spec's
    self-correction pattern) to the LLM for retry."""


class ValidationError(BackendError):
    """Raised when an operation violates a hard rule (e.g. clip doesn't
    exist, source path not in the project). The error message contains
    a `fix:` line with the smallest correction the LLM should make."""


class NotFoundError(BackendError):
    """Raised when a referenced clip/track/effect is not present."""


class CatalogError(BackendError):
    """Raised when an effect/transition id is not in Phase 1's catalog."""


# ---- The interface itself ----


class EditorBackend(ABC):
    """Abstract editor backend. Phase 3 codes against this; concrete
    implementations (file-based, D-Bus-based) live elsewhere.

    Methods that mutate the project do NOT save to disk; call
    `save(path)` explicitly. This keeps "preview an edit" (run
    operations, inspect summary, throw away) trivial."""

    # --- Read operations ---

    @abstractmethod
    def get_project_info(self) -> ProjectInfo: ...

    @abstractmethod
    def get_timeline_summary(self) -> TimelineSummary: ...

    # --- Bin operations ---

    @abstractmethod
    def import_media(self, paths: Sequence[str]) -> list[str]:
        """Add media files to the project bin. Returns the new bin
        entry ids. Paths may be absolute or relative to the project
        directory; relative paths are stored as-is and resolved on save."""

    # --- Timeline operations ---

    @abstractmethod
    def insert_clip(
        self,
        track_index: int,
        position_sec: float,
        source_id: str,
        source_in_sec: float = 0.0,
        source_out_sec: float | None = None,
    ) -> str:
        """Insert a clip from the bin onto the timeline at the given
        position. Returns the new clip id."""

    @abstractmethod
    def append_clip(
        self,
        track_index: int,
        source_id: str,
        source_in_sec: float = 0.0,
        source_out_sec: float | None = None,
    ) -> str:
        """Append a clip to the end of the given track. Returns the
        new clip id."""

    @abstractmethod
    def move_clip(
        self, clip_id: str, new_track: int, new_position_sec: float
    ) -> None: ...

    @abstractmethod
    def trim_clip(
        self, clip_id: str, new_in_sec: float, new_out_sec: float
    ) -> None: ...

    @abstractmethod
    def delete_clip(self, clip_id: str) -> None: ...

    @abstractmethod
    def add_transition(
        self,
        clip_a_id: str,
        clip_b_id: str,
        kind: str = "dissolve",
        duration_sec: float = 1.0,
    ) -> str:
        """Add a transition between two clips on the same track.
        `kind` is a transition kdenlive_id from the catalog
        (e.g. 'dissolve', 'wipe', 'composite'). Returns the new
        transition id."""

    @abstractmethod
    def apply_effect(
        self,
        clip_id: str,
        effect_id: str,
        params: dict | None = None,
    ) -> str:
        """Apply an effect to a clip. `effect_id` is a kdenlive_id from
        the catalog. `params` is a dict of {param_name: value}. Returns
        the new effect instance id. Validates effect_id + param names
        + param types against the Phase 1 catalog."""

    @abstractmethod
    def add_marker(
        self, position_sec: float, label: str, kind: str = "marker"
    ) -> None:
        """Add a marker/guide/chapter at the given position. `kind` is
        one of 'marker' | 'guide' | 'chapter'."""

    # --- Persistence ---

    @abstractmethod
    def save(self, path: str | None = None) -> None:
        """Save the project. If path is None, save to the original
        load path (if any)."""
