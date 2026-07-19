"""KdenliveFileBackend — thin dispatch to ops/*.py.

Every method is a one-liner that delegates to a function in
``phase2_project_engine.ops.*``. The actual logic lives in those
ops modules so it can be tested in isolation without a class.

The corresponding ABC lives in ``backend.py``, and the small
private XML-parsing helpers used by ``get_timeline_summary``
live there too (re-imported below).
"""
from __future__ import annotations

from collections.abc import Sequence

from lxml import etree

from . import ops
from .backend import (
    EditorBackend,
    _entry_to_clip_summary,
    _iter_markers,
    _iter_transitions,
    _track_kind,
)
from .catalog import Catalog
from .io import ProjectTree, _tc_to_sec, load_project, save_project
from .tracks import get_tracks, get_video_playlist
from .types import (
    ClipSummary,
    ProjectInfo,
    TimelineSummary,
    TrackSummary,
)


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
