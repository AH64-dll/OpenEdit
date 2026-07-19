"""EditorBackend (ABC) + KdenliveFileBackend (thin dispatch).

The concrete backend is THIN: every method is a one-line dispatch
to ``ops/*.py``. The actual logic lives in the ops modules so it can
be tested in isolation without a class.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from lxml import etree

from . import ops
from .catalog import Catalog
from .errors import (
    BackendError,
    CatalogError,
    NotFoundError,
    ValidationError,
)
from .io import ProjectTree, _tc_to_sec, load_project, save_project
from .ops._helpers import entry_start_sec
from .tracks import (
    _tc_to_sec as _tc_to_sec_t,
    get_tracks,
    get_video_playlist,
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


class KdenliveFileBackend(EditorBackend):
    """File-based implementation. Each method dispatches to ops/*.py."""

    def __init__(self, project_path: str | None, catalog: Catalog) -> None:
        self.catalog = catalog
        self.tree = (
            self._new_empty_project() if project_path is None
            else load_project(project_path)
        )
        self.tree.ensure_docproperties()

    @staticmethod
    def _new_empty_project() -> ProjectTree:
        mlt = etree.Element("mlt")
        mlt.set("version", "7.40.0")
        mlt.set("producer", "main_bin")
        mlt.set("LC_NUMERIC", "C")
        profile = etree.SubElement(mlt, "profile")
        for k, v in {
            "width": "1920", "height": "1080", "progressive": "1",
            "sample_aspect_num": "1", "sample_aspect_den": "1",
            "frame_rate_num": "30", "frame_rate_den": "1",
            "colorspace": "709", "description": "1920x1080 30.00fps",
            "display_aspect_num": "16", "display_aspect_den": "9",
        }.items():
            profile.set(k, v)
        main_bin = etree.SubElement(mlt, "playlist")
        main_bin.set("id", "main_bin")
        v1 = etree.SubElement(mlt, "playlist")
        v1.set("id", "video_track")
        tractor = etree.SubElement(mlt, "tractor")
        tractor.set("id", "main_tractor")
        tractor.set("in", "00:00:00.000")
        tractor.set("out", "00:00:00.000")
        mt = etree.SubElement(tractor, "multitrack")
        tr = etree.SubElement(mt, "track")
        tr.set("producer", "video_track")
        return ProjectTree(root=mlt, path=None)

    def get_project_info(self) -> ProjectInfo:
        tree = self.tree
        info = tree.get_docproperties()
        tractor = tree.get_tractor()
        return ProjectInfo(
            name=info.get("author", info.get("uuid", "(unnamed)")),
            fps=tree.get_profile_fps(),
            width=tree.get_profile_resolution()[0],
            height=tree.get_profile_resolution()[1],
            colorspace=tree.get_profile().get("colorspace", "709"),
            track_count=len(get_tracks(tree)),
            duration_sec=_tc_to_sec(tractor.get("out", "00:00:00.000"))
            if tractor is not None else 0.0,
            path=str(tree.path) if tree.path else None,
        )

    def get_timeline_summary(self) -> TimelineSummary:
        tree = self.tree
        track_summaries: list[TrackSummary] = []
        clip_summaries: list[ClipSummary] = []
        for i, tr in enumerate(get_tracks(tree)):
            video_pl = get_video_playlist(tree, tr)
            entries = list(video_pl.findall("entry")) if video_pl is not None else []
            track_summaries.append(TrackSummary(
                index=i, kind=_track_kind(tr),
                name=tr.get("id", f"track_{i}"), clip_count=len(entries),
            ))
            for c in entries:
                clip_summaries.append(_entry_to_clip_summary(c, i, video_pl, tree))
        return TimelineSummary(
            project=self.get_project_info(),
            tracks=tuple(track_summaries),
            clips=tuple(clip_summaries),
            transitions=tuple(_iter_transitions(tree)),
            markers=tuple(_iter_markers(tree)),
        )

    def import_media(self, paths: Sequence[str]) -> list[str]:
        return ops.import_media(self.tree, paths)

    def insert_clip(self, track_index, position_sec, source_id, source_in_sec=0.0,
                    source_out_sec=None, video_only=False, audio_only=False):
        return ops.insert_clip(
            self.tree, track_index=track_index, position_sec=position_sec,
            source_id=source_id, source_in_sec=source_in_sec,
            source_out_sec=source_out_sec, video_only=video_only, audio_only=audio_only,
        )

    def append_clip(self, track_index, source_id, source_in_sec=0.0,
                    source_out_sec=None, video_only=False, audio_only=False):
        return ops.append_clip(
            self.tree, track_index=track_index, source_id=source_id,
            source_in_sec=source_in_sec, source_out_sec=source_out_sec,
            video_only=video_only, audio_only=audio_only,
        )

    def move_clip(self, clip_id, new_track, new_position_sec):
        ops.move_clip(self.tree, clip_id, new_track=new_track, new_position_sec=new_position_sec)

    def trim_clip(self, clip_id, new_in_sec, new_out_sec):
        ops.trim_clip(self.tree, clip_id, new_in_sec=new_in_sec, new_out_sec=new_out_sec)

    def delete_clip(self, clip_id):
        ops.delete_clip(self.tree, clip_id)

    def add_transition(self, clip_a_id, clip_b_id, kind="dissolve", duration_sec=1.0):
        return ops.add_transition(
            self.tree, catalog=self.catalog.transitions,
            clip_a_id=clip_a_id, clip_b_id=clip_b_id, kind=kind, duration_sec=duration_sec,
        )

    def remove_transition(self, transition_id):
        return ops.remove_transition(self.tree, transition_id=transition_id)

    def apply_effect(self, clip_id, effect_id, params=None):
        return ops.apply_effect(self.tree, clip_id, effect_id, params,
                                catalog=self.catalog.effects)

    def remove_effect(self, clip_id, effect_index):
        return ops.remove_effect(self.tree, clip_id, effect_index)

    def add_marker(self, position_sec, label, kind="marker"):
        ops.add_marker(self.tree, position_sec, label, kind)

    def slip_clip(self, clip_id, delta_sec):
        return ops.slip_clip(self.tree, clip_id, delta_sec=delta_sec)

    def ripple_delete_clip(self, clip_id):
        return ops.ripple_delete_clip(self.tree, clip_id)

    def change_clip_speed(self, clip_id, rate):
        return ops.change_clip_speed(self.tree, clip_id, rate=rate)

    def split_clip(self, clip_id, at_sec):
        return ops.split_clip(self.tree, clip_id, at_sec=at_sec)

    def replace_clip_source(self, clip_id, new_source_id):
        return ops.replace_clip_source(self.tree, clip_id, new_source_id=new_source_id)

    def group_clips(self, clip_ids, group_name):
        return ops.group_clips(self.tree, clip_ids, group_name)

    def ungroup_clips(self, group_name):
        return ops.ungroup_clips(self.tree, group_name)

    def list_groups(self):
        return ops.list_groups(self.tree)

    def save(self, path=None):
        save_project(self.tree, path)


# --- Private helpers ---------------------------------------------------------


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


__all__ = [
    "EditorBackend", "KdenliveFileBackend",
    "ProjectInfo", "ClipSummary", "TrackSummary",
    "TransitionSummary", "MarkerSummary", "EffectSummary", "TimelineSummary",
    "BackendError", "ValidationError", "NotFoundError", "CatalogError",
]
