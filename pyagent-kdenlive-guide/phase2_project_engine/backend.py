"""EditorBackend (ABC) + small private helpers.

Defines the abstract interface that Phase 3 codes against, plus a
handful of private XML-parsing helpers used by the file-based
implementation in ``backend_dispatch.py``.

The concrete ``KdenliveFileBackend`` lives in ``backend_dispatch.py``
and is re-exported from this module so existing import paths keep
working:

    from phase2_project_engine import KdenliveFileBackend
    from phase2_project_engine.backend import KdenliveFileBackend
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from lxml import etree

from .errors import (
    BackendError,
    CatalogError,
    NotFoundError,
    ValidationError,
)
from .ops._helpers import entry_start_sec
from .tracks import (
    _tc_to_sec as _tc_to_sec_t,
)
from .types import (
    ClipSummary,
    EffectSummary,
    MarkerSummary,
    ProjectInfo,
    TimelineSummary,
    TrackSummary,
    TransitionSummary,
)


class EditorBackend(ABC):
    """Abstract editor backend. Phase 3 codes against this."""

    @abstractmethod
    def get_project_info(self) -> ProjectInfo: ...
    @abstractmethod
    def get_timeline_summary(self) -> TimelineSummary: ...
    @abstractmethod
    def import_media(self, paths: Sequence[str]) -> list[str]: ...
    @abstractmethod
    def insert_clip(self, track_index: int, position_sec: float, source_id: str,
                    source_in_sec: float = 0.0, source_out_sec: float | None = None,
                    video_only: bool = False, audio_only: bool = False) -> str: ...
    @abstractmethod
    def append_clip(self, track_index: int, source_id: str,
                    source_in_sec: float = 0.0, source_out_sec: float | None = None,
                    video_only: bool = False, audio_only: bool = False) -> str: ...
    @abstractmethod
    def move_clip(self, clip_id: str, new_track: int, new_position_sec: float) -> None: ...
    @abstractmethod
    def trim_clip(self, clip_id: str, new_in_sec: float, new_out_sec: float) -> None: ...
    @abstractmethod
    def delete_clip(self, clip_id: str) -> None: ...
    @abstractmethod
    def add_transition(self, clip_a_id: str, clip_b_id: str,
                       kind: str = "dissolve", duration_sec: float = 1.0) -> str: ...
    @abstractmethod
    def remove_transition(self, transition_id: str) -> dict: ...
    @abstractmethod
    def apply_effect(self, clip_id: str, effect_id: str,
                     params: dict | None = None) -> str: ...
    @abstractmethod
    def remove_effect(self, clip_id: str, effect_index: int) -> dict: ...
    @abstractmethod
    def add_marker(self, position_sec: float, label: str, kind: str = "marker") -> None: ...
    @abstractmethod
    def slip_clip(self, clip_id: str, delta_sec: float) -> dict: ...
    @abstractmethod
    def ripple_delete_clip(self, clip_id: str) -> dict: ...
    @abstractmethod
    def change_clip_speed(self, clip_id: str, rate: float) -> dict: ...
    @abstractmethod
    def split_clip(self, clip_id: str, at_sec: float) -> dict: ...
    @abstractmethod
    def replace_clip_source(self, clip_id: str, new_source_id: str) -> dict: ...
    @abstractmethod
    def group_clips(self, clip_ids: list[str], group_name: str) -> dict: ...
    @abstractmethod
    def ungroup_clips(self, group_name: str) -> dict: ...
    @abstractmethod
    def list_groups(self) -> dict: ...
    @abstractmethod
    def save(self, path: str | None = None) -> None: ...


# --- Private helpers ---------------------------------------------------------
#
# These are XML-parsing utilities used by KdenliveFileBackend.get_timeline_summary.
# They live here (rather than in backend_dispatch.py) so the concrete class
# file stays focused on the dispatch surface; they are also small enough that
# the cost of importing them from the concrete class is negligible.


def _track_kind(tr: etree._Element) -> str:
    kt = tr.find("property[@name='kdenlive:track_type']")
    if kt is not None and kt.text in ("audio", "video"):
        return kt.text
    at = tr.find("property[@name='kdenlive:audio_track']")
    if at is not None and at.text == "1":
        return "audio"
    return "video"


def _entry_to_clip_summary(entry, track_index, playlist, tree):
    kid = ""
    for p in entry.iter("property"):
        if p.get("name") == "kdenlive:id":
            kid = p.text or ""
            break
    prod_id = entry.get("producer", "")
    source_path, source_name, source_kid = "", "", ""
    for prod in tree.root.iter("producer"):
        if prod.get("id") == prod_id:
            for p in prod.iter("property"):
                if p.get("name") == "resource":
                    source_path = p.text or ""
                    source_name = source_path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
                elif p.get("name") == "kdenlive:id":
                    source_kid = p.text or ""
            break
    effects: list[str] = []
    for f in entry.iter("filter"):
        for p in f.iter("property"):
            if p.get("name") == "kdenlive:id":
                effects.append(p.text or "")
                break
    start = entry_start_sec(playlist, entry)
    in_val = _tc_to_sec_t(entry.get("in", "00:00:00.000"))
    out_val = _tc_to_sec_t(entry.get("out", "00:00:00.000"))
    return ClipSummary(
        clip_id=kid, track_index=track_index, start_sec=start,
        end_sec=start + max(0.0, out_val - in_val),
        source_id=source_kid, source_path=source_path, source_name=source_name,
        source_in_sec=in_val, source_out_sec=out_val, effects=tuple(effects),
    )


def _iter_transitions(tree):
    for tr in tree.root.iter("transition"):
        kid = ""
        a_track = 0
        mlt = ""
        for p in tr.iter("property"):
            n = p.get("name")
            if n == "kdenlive:id":
                kid = p.text or ""
            elif n == "a_track" and (p.text or "").isdigit():
                a_track = int(p.text)
            elif n == "mlt_service":
                mlt = p.text or ""
        yield TransitionSummary(
            transition_id=kid, track_index=a_track,
            start_sec=_tc_to_sec_t(tr.get("in", "00:00:00.000")),
            end_sec=_tc_to_sec_t(tr.get("out", "00:00:00.000")),
            kind=mlt or tr.get("id", "transition"),
        )


def _iter_markers(tree):
    for m in tree.root.iter("marker"):
        time, label, kind = 0.0, "", "marker"
        for p in m.iter("property"):
            n = p.get("name")
            if n == "time":
                time = _tc_to_sec_t(p.text or "00:00:00.000")
            elif n == "comment":
                label = p.text or ""
            elif n == "type":
                kind = {0: "marker", 1: "guide", 2: "chapter"}.get(int(p.text or 0), "marker")
        yield MarkerSummary(position_sec=time, label=label, kind=kind)


# Re-export the concrete implementation at the bottom of the module so the
# circular import resolves: backend_dispatch imports EditorBackend and the
# private helpers from this module (defined above), and we re-import
# KdenliveFileBackend from backend_dispatch here.
from .backend_dispatch import KdenliveFileBackend  # noqa: E402


__all__ = [
    "EditorBackend", "KdenliveFileBackend",
    "ProjectInfo", "ClipSummary", "TrackSummary",
    "TransitionSummary", "MarkerSummary", "EffectSummary", "TimelineSummary",
    "BackendError", "ValidationError", "NotFoundError", "CatalogError",
]
