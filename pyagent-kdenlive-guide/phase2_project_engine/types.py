"""Public dataclasses returned by the editor backend.

These are the only types that flow OUT of the backend (via tool
results) and INTO the backend (via tool args). The shape of these
types IS the contract that the LLM sees; do not change field names
without updating `phase3_pyagent_core/tests/test_golden_io.py`.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProjectInfo:
    name: str
    fps: float
    width: int
    height: int
    colorspace: str
    track_count: int
    duration_sec: float
    path: str | None


@dataclass(frozen=True)
class ClipSummary:
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
class TrackSummary:
    index: int
    kind: str
    name: str
    clip_count: int


@dataclass(frozen=True)
class TransitionSummary:
    transition_id: str
    track_index: int
    start_sec: float
    end_sec: float
    kind: str


@dataclass(frozen=True)
class MarkerSummary:
    position_sec: float
    label: str
    kind: str


@dataclass(frozen=True)
class EffectSummary:
    effect_id: str
    clip_id: str
    params: dict[str, str]


__all__ = [
    "ProjectInfo", "ClipSummary", "TrackSummary",
    "TransitionSummary", "MarkerSummary", "EffectSummary",
]
