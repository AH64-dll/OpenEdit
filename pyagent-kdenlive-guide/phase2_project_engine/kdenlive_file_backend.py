"""
kdenlive_file_backend.py — Backend A: file-based, lxml-only.

Phase 3 (and any future caller) uses the KdenliveFileBackend class
to manipulate a .kdenlive project. The class implements every method
in editor_backend.EditorBackend.

Design points worth flagging:

1. **The catalog is loaded once at construction time.** It's used to
   validate effect/transition ids and parameter types. Backend doesn't
   reach out to disk for it after __init__.

2. **All clip / track ids are stable across save/load.** Kdenlive's
   `kdenlive:id` numeric scheme is preserved; new entries get the
   next free number. This means PyAgent can save a project, the
   human can re-open it in Kdenlive, save again, and PyAgent's
   in-memory `clip_id`s still resolve (because they map to
   `kdenlive:id` and that survives the round trip).

3. **Operations are NOT persistent until save().** Multiple edits
   compose: e.g. `insert_clip(A); insert_clip(B); add_transition(A, B);
   save()`.

4. **Round-trip safety:** the engine never deletes a property or
   element that it doesn't have a reason to delete. New properties
   are added at the end of their parent; the rest of the XML is
   preserved verbatim. This is what makes "open, do nothing, save"
   produce a semantically-identical file.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lxml import etree

from .editor_backend import (
    BackendError,
    CatalogError,
    ClipSummary,
    EditorBackend,
    MarkerSummary,
    ProjectInfo,
    TimelineSummary,
    TrackSummary,
    TransitionSummary,
)
from .validation import ValidationError  # canonical
from .tracks import get_video_playlist
from .io import (
    ProjectTree,
    _sec_to_tc,
    _tc_to_sec,
    load_project,
    save_project,
)
from .validation import (
    validate_clip_range,
    validate_effect_id,
    validate_effect_params,
    validate_marker_kind,
    validate_position_sec,
    validate_source_path,
    validate_track_index,
    validate_transition_kind,
)


def _playlist_duration(pl: etree._Element | None) -> float:
    if pl is None:
        return 0.0
    duration = 0.0
    for child in pl:
        if child.tag == "entry":
            in_val = _tc_to_sec(child.get("in", "00:00:00.000"))
            out_val = _tc_to_sec(child.get("out", "00:00:00.000"))
            duration += max(0.0, out_val - in_val)
        elif child.tag == "blank":
            duration += _tc_to_sec(child.get("length", "00:00:00.000"))
    return duration


def _entry_start_sec(pl: etree._Element | None, entry: etree._Element) -> float:
    if pl is None:
        return 0.0
    current_time = 0.0
    for child in pl:
        if child == entry:
            return current_time
        if child.tag == "entry":
            in_val = _tc_to_sec(child.get("in", "00:00:00.000"))
            out_val = _tc_to_sec(child.get("out", "00:00:00.000"))
            current_time += max(0.0, out_val - in_val)
        elif child.tag == "blank":
            current_time += _tc_to_sec(child.get("length", "00:00:00.000"))
    return current_time


def _shift_entry_on_timeline(pl: etree._Element, entry: etree._Element, shift: float) -> None:
    if shift == 0.0:
        return
    idx = list(pl).index(entry)
    if idx > 0 and pl[idx - 1].tag == "blank":
        blank = pl[idx - 1]
        old_len = _tc_to_sec(blank.get("length", "00:00:00.000"))
        new_len = max(0.0, old_len + shift)
        if new_len > 0.0:
            blank.set("length", _sec_to_tc(new_len))
        else:
            pl.remove(blank)
    elif shift > 0.0:
        blank = etree.Element("blank")
        blank.set("length", _sec_to_tc(shift))
        pl.insert(idx, blank)


def _insert_entry_at_position(pl: etree._Element, entry: etree._Element, position_sec: float) -> None:
    items = []
    for child in pl:
        if child == entry:
            continue
        if child.tag == "entry":
            items.append((
                child,
                _tc_to_sec(child.get("in", "00:00:00.000")),
                _tc_to_sec(child.get("out", "00:00:00.000"))
            ))
        elif child.tag == "blank":
            items.append((
                child,
                _tc_to_sec(child.get("length", "00:00:00.000"))
            ))

    for child in list(pl):
        pl.remove(child)

    current_time = 0.0
    inserted = False

    entry_dur = _tc_to_sec(entry.get("out", "00:00:00.000")) - _tc_to_sec(entry.get("in", "00:00:00.000"))

    def add_our_entry():
        nonlocal inserted
        pl.append(entry)
        inserted = True

    for item in items:
        if not inserted:
            item_dur = (item[2] - item[1] if len(item) == 3 else item[1])
            if current_time <= position_sec < current_time + item_dur:
                diff = position_sec - current_time
                if diff > 0.0:
                    if len(item) == 2:
                        b = etree.Element("blank")
                        b.set("length", _sec_to_tc(diff))
                        pl.append(b)
                    else:
                        left = etree.Element("entry")
                        left.set("producer", item[0].get("producer"))
                        left.set("in", _sec_to_tc(item[1]))
                        left.set("out", _sec_to_tc(item[1] + diff))
                        for c in item[0]:
                            left.append(c)
                        pl.append(left)

                add_our_entry()

                right_dur = item_dur - diff
                if right_dur > 0.0:
                    if len(item) == 2:
                        b = etree.Element("blank")
                        b.set("length", _sec_to_tc(right_dur))
                        pl.append(b)
                    else:
                        right = etree.Element("entry")
                        right.set("producer", item[0].get("producer"))
                        right.set("in", _sec_to_tc(item[1] + diff))
                        right.set("out", _sec_to_tc(item[2]))
                        for c in item[0]:
                            right.append(c)
                        pl.append(right)
                continue

        pl.append(item[0])
        current_time += (item[2] - item[1] if len(item) == 3 else item[1])

    if not inserted:
        if position_sec > current_time:
            blank = etree.Element("blank")
            blank.set("length", _sec_to_tc(position_sec - current_time))
            pl.append(blank)
        add_our_entry()


@dataclass
class Catalog:
    """In-memory snapshot of Phase 1's catalog.json. Loaded once at
    KdenliveFileBackend construction; not mutated."""

    effects: list[dict]
    transitions: list[dict]
    generators: list[dict]
    by_id: dict[str, dict]

    @classmethod
    def from_json(cls, path: str | Path) -> "Catalog":
        data = json.loads(Path(path).read_text())
        all_entries = data["effects"] + data["transitions"] + data["generators"]
        by_id: dict[str, dict] = {}
        for e in all_entries:
            kid = e.get("kdenlive_id")
            if kid:
                by_id[kid] = e
        return cls(
            effects=data["effects"],
            transitions=data["transitions"],
            generators=data["generators"],
            by_id=by_id,
        )


class KdenliveFileBackend(EditorBackend):
    """File-based implementation of EditorBackend. Wraps a ProjectTree
    and dispatches operations to it. Operations are NOT persisted to
    disk until `save()` is called."""

    def __init__(self, project_path: str | Path | None, catalog: Catalog):
        self.catalog = catalog
        if project_path is None:
            self.tree = self._new_empty_project()
        else:
            self.tree = load_project(project_path)
        # Ensure doc-properties are present (closes the "Untitled" gap).
        self.tree.ensure_docproperties()
        # Bump modified timestamp.
        self._touch_modified()

    # --- Construction ---

    @staticmethod
    def _new_empty_project() -> ProjectTree:
        """Create a minimal in-memory Kdenlive project."""
        mlt = etree.Element("mlt")
        mlt.set("version", "7.40.0")
        mlt.set("producer", "main_bin")
        mlt.set("LC_NUMERIC", "C")
        profile = etree.SubElement(mlt, "profile")
        profile.set("width", "1920")
        profile.set("height", "1080")
        profile.set("progressive", "1")
        profile.set("sample_aspect_num", "1")
        profile.set("sample_aspect_den", "1")
        profile.set("frame_rate_num", "30")
        profile.set("frame_rate_den", "1")
        profile.set("colorspace", "709")
        profile.set("description", "1920x1080 30.00fps")
        profile.set("display_aspect_num", "16")
        profile.set("display_aspect_den", "9")
        # main_bin playlist
        main_bin = etree.SubElement(mlt, "playlist")
        main_bin.set("id", "main_bin")
        # One default video track
        v1 = etree.SubElement(mlt, "playlist")
        v1.set("id", "video_track")
        # Tractor
        tractor = etree.SubElement(mlt, "tractor")
        tractor.set("id", "main_tractor")
        tractor.set("in", "00:00:00.000")
        tractor.set("out", "00:00:00.000")
        mt = etree.SubElement(tractor, "multitrack")
        tr = etree.SubElement(mt, "track")
        tr.set("producer", "video_track")
        return ProjectTree(root=mlt, path=None)

    # --- Read operations ---

    def get_project_info(self) -> ProjectInfo:
        tree = self.tree
        info = tree.get_docproperties()
        return ProjectInfo(
            name=info.get("author", info.get("uuid", "(unnamed)")),
            fps=tree.get_profile_fps(),
            width=tree.get_profile_resolution()[0],
            height=tree.get_profile_resolution()[1],
            colorspace=tree.get_profile().get("colorspace", "709"),
            track_count=len(tree.get_tracks()),
            duration_sec=_tc_to_sec(tree.get_tractor().get("out", "00:00:00.000"))
            if tree.get_tractor() is not None
            else 0.0,
            path=str(tree.path) if tree.path else None,
        )

    def get_timeline_summary(self) -> TimelineSummary:
        tree = self.tree
        tracks = tree.get_tracks()
        track_summaries: list[TrackSummary] = []
        clip_summaries: list[ClipSummary] = []
        trans_summaries: list[TransitionSummary] = []
        for i, tr in enumerate(tracks):
            # Each user-facing track is a <tractor> with child playlists
            # (video + audio). The video playlist is what holds the visible
            # entries on the timeline.
            video_pl = get_video_playlist(tree, tr)
            entries = list(video_pl.findall("entry")) if video_pl is not None else []
            # Track kind/name from the tractor's properties if present.
            kind = "video"
            at = tr.find("property[@name='kdenlive:audio_track']")
            if at is not None and at.text == "1":
                kind = "audio"
            kt = tr.find("property[@name='kdenlive:track_type']")
            if kt is not None and kt.text in ("audio", "video"):
                kind = kt.text
            track_summaries.append(
                TrackSummary(
                    index=i,
                    kind=kind,
                    name=tr.get("id", f"track_{i}"),
                    clip_count=len(entries),
                )
            )
            for c in entries:
                clip_summaries.append(_entry_to_clip_summary(c, i, video_pl, tree))
        # Transitions live inside the <tractor> in Kdenlive, not the
        # playlist. Walk every <transition> and figure out its track.
        for tr in tree.root.iter("transition"):
            a_track = 0
            for p in tr.iter("property"):
                if p.get("name") == "a_track" and (p.text or "").isdigit():
                    a_track = int(p.text)
                    break
            trans_summaries.append(_transition_to_summary(tr, a_track, None))
        markers = list(_iter_markers(tree))
        return TimelineSummary(
            project=self.get_project_info(),
            tracks=tuple(track_summaries),
            clips=tuple(clip_summaries),
            transitions=tuple(trans_summaries),
            markers=tuple(markers),
        )

    # --- Bin operations ---

    def import_media(self, paths: Sequence[str]) -> list[str]:
        bin_el = self.tree.get_main_bin()
        if bin_el is None:
            raise BackendError("project has no main_bin playlist")
        new_ids: list[str] = []
        for p in paths:
            abs_path = validate_source_path(p)
            # CRITICAL: producers must be children of the MLT root, not the
            # main_bin playlist. If they go inside main_bin, MLT silently
            # drops them (Property without a parent warnings) and the
            # timeline shows empty. Also, they must be defined BEFORE any
            # playlist/tractor references them. So we insert them before the
            # first playlist or tractor element.
            insert_idx = 0
            for idx, child in enumerate(self.tree.root):
                if child.tag in ("playlist", "tractor", "transition", "filter"):
                    insert_idx = idx
                    break
            else:
                insert_idx = len(self.tree.root)
            producer = etree.Element("producer")
            self.tree.root.insert(insert_idx, producer)
            producer.set("id", f"producer_{len(self.tree.root) - 1}")
            resource = etree.SubElement(producer, "property")
            resource.set("name", "resource")
            resource.text = str(abs_path)
            self.tree.ensure_kdenlive_properties_on_producer(producer, str(abs_path))
            # The new producer's kdenlive:id is what callers will use to
            # reference it as a `source_id` in insert_clip/append_clip.
            kid = next(
                (
                    p.text
                    for p in producer.iter("property")
                    if p.get("name") == "kdenlive:id"
                ),
                None,
            )
            if kid is None:
                raise BackendError(
                    f"internal error: imported {abs_path} has no kdenlive:id"
                )
            new_ids.append(kid)
        self._touch_modified()
        return new_ids

    # --- Timeline operations ---

    def insert_clip(
        self,
        track_index: int,
        position_sec: float,
        source_id: str,
        source_in_sec: float = 0.0,
        source_out_sec: float | None = None,
        video_only: bool = False,
        audio_only: bool = False,
    ) -> str:
        tracks = self.tree.get_tracks()
        validate_track_index(track_index, len(tracks))
        validate_position_sec(position_sec)
        if source_out_sec is None:
            source_out_sec = self._resolve_source_duration(source_id)
        validate_clip_range(source_in_sec, source_out_sec, self._resolve_source_duration(source_id))

        is_audio = self._is_audio_track(track_index)
        if is_audio:
            target_audio_track = track_index
            target_video_track = self._get_paired_track_index(track_index)
        else:
            target_video_track = track_index
            target_audio_track = self._get_paired_track_index(track_index)

        producer = self._resolve_producer_by_id(source_id)
        kid = self._next_kdenlive_id()

        # Insert Video Part
        if not audio_only and target_video_track is not None:
            tractor = tracks[target_video_track]
            pl = get_video_playlist(self.tree, tractor)
            if pl is not None:
                new_entry = etree.Element("entry")
                new_entry.set("producer", producer.get("id"))
                new_entry.set("in", _sec_to_tc(source_in_sec))
                new_entry.set("out", _sec_to_tc(source_out_sec))
                _insert_entry_at_position(pl, new_entry, position_sec)
                
                new_id = etree.SubElement(new_entry, "property")
                new_id.set("name", "kdenlive:id")
                new_id.text = kid

        # Insert Audio Part
        if not video_only and target_audio_track is not None and self._producer_has_audio(producer):
            tractor = tracks[target_audio_track]
            pl = get_video_playlist(self.tree, tractor)
            if pl is None:
                playlists = self.tree.get_track_playlists(tractor)
                pl = playlists[0] if playlists else None
            
            if pl is not None:
                new_entry = etree.Element("entry")
                new_entry.set("producer", producer.get("id"))
                new_entry.set("in", _sec_to_tc(source_in_sec))
                new_entry.set("out", _sec_to_tc(source_out_sec))
                _insert_entry_at_position(pl, new_entry, position_sec)
                
                new_id = etree.SubElement(new_entry, "property")
                new_id.set("name", "kdenlive:id")
                new_id.text = kid

        self._bump_tractor_duration()
        self._touch_modified()
        return kid

    def append_clip(
        self,
        track_index: int,
        source_id: str,
        source_in_sec: float = 0.0,
        source_out_sec: float | None = None,
        video_only: bool = False,
        audio_only: bool = False,
    ) -> str:
        tracks = self.tree.get_tracks()
        validate_track_index(track_index, len(tracks))
        if source_out_sec is None:
            source_out_sec = self._resolve_source_duration(source_id)
        # Position at the end of the track.
        video_pl = get_video_playlist(self.tree, tracks[track_index])
        if video_pl is None:
            playlists = self.tree.get_track_playlists(tracks[track_index])
            video_pl = playlists[0] if playlists else None
        last_end = _playlist_duration(video_pl)
        return self.insert_clip(
            track_index=track_index,
            position_sec=last_end,
            source_id=source_id,
            source_in_sec=source_in_sec,
            source_out_sec=source_out_sec,
            video_only=video_only,
            audio_only=audio_only,
        )

    def move_clip(
        self, clip_id: str, new_track: int, new_position_sec: float
    ) -> None:
        entries = self._find_all_entries(clip_id)
        if not entries:
            raise BackendError(f"no clip with kdenlive:id='{clip_id}' on any track")
        validate_track_index(new_track, len(self.tree.get_tracks()))
        validate_position_sec(new_position_sec)
        
        for entry, track_idx in entries:
            # Remove from current track
            parent = entry.getparent()
            if parent is not None:
                parent.remove(entry)
            
            # Determine target track
            if self._is_audio_track(track_idx):
                target_track = self._get_paired_track_index(new_track)
                if target_track is None:
                    tracks = self.tree.get_tracks()
                    audio_indices = [i for i, tr in enumerate(tracks) if tr.find("property[@name='kdenlive:audio_track']") is not None and tr.find("property[@name='kdenlive:audio_track']").text == "1"]
                    target_track = audio_indices[0] if audio_indices else new_track
            else:
                target_track = new_track
            
            target_tractor = self.tree.get_tracks()[target_track]
            pl = get_video_playlist(self.tree, target_tractor)
            if pl is None:
                playlists = self.tree.get_track_playlists(target_tractor)
                pl = playlists[0] if playlists else None
            
            if pl is None:
                raise BackendError(f"track {target_track} has no writable playlist")
            
            _insert_entry_at_position(pl, entry, new_position_sec)
        self._touch_modified()

    def trim_clip(
        self, clip_id: str, new_in_sec: float, new_out_sec: float
    ) -> None:
        entries = self._find_all_entries(clip_id)
        if not entries:
            raise BackendError(f"no clip with kdenlive:id='{clip_id}' on any track")
        
        first_entry = entries[0][0]
        source_id = self._find_clip_source_kdenlive_id(first_entry)
        source_duration = self._resolve_source_duration(source_id)
        validate_clip_range(new_in_sec, new_out_sec, source_duration)
        
        for entry, _ in entries:
            old_in_sec = _tc_to_sec(entry.get("in", "00:00:00.000"))
            entry.set("in", _sec_to_tc(new_in_sec))
            entry.set("out", _sec_to_tc(new_out_sec))
            
            parent = entry.getparent()
            if parent is not None:
                diff = new_in_sec - old_in_sec
                _shift_entry_on_timeline(parent, entry, diff)
                
        self._bump_tractor_duration()
        self._touch_modified()

    def delete_clip(self, clip_id: str) -> None:
        entries = self._find_all_entries(clip_id)
        if not entries:
            raise BackendError(f"no clip with kdenlive:id='{clip_id}' on any track")
        for entry, _ in entries:
            parent = entry.getparent()
            if parent is not None:
                parent.remove(entry)
        self._bump_tractor_duration()
        self._touch_modified()

    def add_transition(
        self,
        clip_a_id: str,
        clip_b_id: str,
        kind: str = "dissolve",
        duration_sec: float = 1.0,
    ) -> str:
        kid = validate_transition_kind(kind, self.catalog.transitions)
        a, track_a = self._find_entry(clip_a_id)
        b, track_b = self._find_entry(clip_b_id)
        if track_a != track_b:
            raise ValidationError(
                f"clips {clip_a_id} and {clip_b_id} are on different tracks; "
                f"transitions are per-track in v1",
                "fix: call move_clip to put both clips on the same track, "
                "then add_transition",
            )
        # In Kdenlive, transitions live INSIDE the <tractor> (as
        # siblings of <track>), not inside the playlist. See the
        # manual_baseline.kdenlive fixture: a transition is e.g.
        #   <tractor>
        #     <track producer="playlist0"/>
        #     <track producer="playlist1"/>
        #     <transition id="transition0" in=... out=...>
        #       <property name="a_track">0</property>
        #       <property name="b_track">1</property>
        #       <property name="mlt_service">mix</property>
        #     </transition>
        # For a same-track crossfade, a_track == b_track.
        tractor = self.tree.get_tractor()
        if tractor is None:
            raise BackendError(
                "project has no tractor; cannot add a transition"
            )
        tr = etree.Element("transition")
        tr.set("id", f"transition_{self._next_numerical_id()}")
        # Timing: cover the boundary from duration/2 before to duration/2
        # after the cut point.
        a_out = _tc_to_sec(a.get("out", "00:00:00.000"))
        tr.set("in", _sec_to_tc(a_out - duration_sec / 2))
        tr.set("out", _sec_to_tc(a_out + duration_sec / 2))
        # Same-track transition: a_track == b_track == track_a.
        for name, val in (("a_track", str(track_a)), ("b_track", str(track_a))):
            p = etree.SubElement(tr, "property")
            p.set("name", name)
            p.text = val
        cat_entry = self.catalog.by_id.get(kid, {})
        mlt = etree.SubElement(tr, "property")
        mlt.set("name", "mlt_service")
        mlt.text = cat_entry.get("mlt_service", kid)
        # Insert in the tractor AFTER the last <track> (Kdenlive's
        # convention; melt accepts the order loosely but this is
        # the order a real Kdenlive save produces).
        last_track_idx = -1
        for i, c in enumerate(tractor):
            if c.tag == "track":
                last_track_idx = i
        tractor.insert(last_track_idx + 1, tr)
        kid2 = self._next_kdenlive_id()
        new_id = etree.SubElement(tr, "property")
        new_id.set("name", "kdenlive:id")
        new_id.text = kid2
        self._touch_modified()
        return kid2

    def apply_effect(
        self,
        clip_id: str,
        effect_id: str,
        params: dict | None = None,
    ) -> str:
        kid = validate_effect_id(effect_id, self.catalog.effects)
        cat_entry = self.catalog.by_id.get(kid)
        if cat_entry is None:
            raise CatalogError(
                f"effect '{kid}' is in the catalog id-index but missing its entry"
            )
        entry, _ = self._find_entry(clip_id)
        filt = etree.SubElement(entry, "filter")
        mlt = etree.SubElement(filt, "property")
        mlt.set("name", "mlt_service")
        mlt.text = cat_entry.get("mlt_service", kid)
        kdenlive_label = etree.SubElement(filt, "property")
        kdenlive_label.set("name", "kdenlive_id")
        kdenlive_label.text = kid
        validated = validate_effect_params(cat_entry, params or {})
        for k, v in validated.items():
            p = etree.SubElement(filt, "property")
            p.set("name", k)
            p.text = v
        self._touch_modified()
        return kid

    def add_marker(
        self, position_sec: float, label: str, kind: str = "marker"
    ) -> None:
        validate_position_sec(position_sec)
        kind = validate_marker_kind(kind)
        tractor = self.tree.get_tractor()
        if tractor is None:
            raise BackendError("project has no tractor (cannot add markers)")
        m = etree.SubElement(tractor, "marker")
        t = etree.SubElement(m, "property")
        t.set("name", "time")
        t.text = _sec_to_tc(position_sec)
        c = etree.SubElement(m, "property")
        c.set("name", "comment")
        c.text = label
        ty = etree.SubElement(m, "property")
        ty.set("name", "type")
        ty.text = {"marker": "0", "guide": "1", "chapter": "2"}[kind]
        self._touch_modified()

    # --- Persistence ---

    def save(self, path: str | Path | None = None) -> None:
        save_project(self.tree, path)

    # --- Internals ---

    def _resolve_producer_by_id(self, kdenlive_id: str) -> etree._Element:
        """Resolve a bin producer from any id form the caller might pass.

        Accepts:
          * the producer's `kdenlive:id` property (e.g. "1", "21"),
          * the MLT producer `id` attribute (e.g. "producer_41"),
          * a timeline ENTRY's `kdenlive:id` (e.g. "12") — we follow
            the entry's `producer` attribute to the real bin producer.
        This keeps append_clip/insert_clip working no matter which id
        the agent read from get_timeline_summary().
        """
        # 1) producer's kdenlive:id property
        for prod in self.tree.root.iter("producer"):
            for p in prod.iter("property"):
                if p.get("name") == "kdenlive:id" and p.text == kdenlive_id:
                    return prod
        # 2) MLT producer id attribute (e.g. "producer_41")
        for prod in self.tree.root.iter("producer"):
            if prod.get("id") == kdenlive_id:
                return prod
        # 3) a timeline entry's kdenlive:id -> resolve its producer
        for pl in self.tree.get_tracks():
            for entry in pl.iter("entry"):
                for p in entry.iter("property"):
                    if p.get("name") == "kdenlive:id" and p.text == kdenlive_id:
                        return self._resolve_producer_by_id(entry.get("producer", ""))
        raise BackendError(
            f"no bin entry with kdenlive:id='{kdenlive_id}'",
            "fix: call import_media() with the source path first, then "
            "use the returned id, or pass the bin producer's kdenlive:id "
            "from get_timeline_summary()'s source_id field",
        )

    def _resolve_source_duration(self, kdenlive_id: str) -> float:
        prod = self._resolve_producer_by_id(kdenlive_id)
        for p in prod.iter("property"):
            if p.get("name") == "kdenlive:duration":
                return _tc_to_sec(p.text or "0")
        # Fallback: use ffprobe on the resource path
        for p in prod.iter("property"):
            if p.get("name") == "resource":
                from .kdenlive_xml import _probe_duration_sec
                return _probe_duration_sec(Path(p.text))
        return 0.0

    def _find_entry(
        self, clip_id: str
    ) -> tuple[etree._Element, int]:
        for i, tr in enumerate(self.tree.get_tracks()):
            for pl in self.tree.get_track_playlists(tr):
                for entry in pl.iter("entry"):
                    for p in entry.iter("property"):
                        if p.get("name") == "kdenlive:id" and p.text == clip_id:
                            return entry, i
        raise BackendError(
            f"no clip with kdenlive:id='{clip_id}' on any track",
            "fix: call get_timeline_summary() to see the current clip ids",
        )

    def _find_clip_source_kdenlive_id(self, entry: etree._Element) -> str:
        """Find the kdenlive:id of the producer referenced by an entry."""
        prod_id = entry.get("producer")
        if prod_id is None:
            raise BackendError(f"entry has no producer attribute: {entry.attrib}")
        for prod in self.tree.root.iter("producer"):
            if prod.get("id") == prod_id:
                for p in prod.iter("property"):
                    if p.get("name") == "kdenlive:id":
                        return p.text or ""
        raise BackendError(
            f"entry references producer id='{prod_id}' which is not in the project"
        )

    def _next_kdenlive_id(self) -> str:
        used = set()
        for p in self.tree.root.iter("property"):
            if p.get("name") == "kdenlive:id" and (p.text or "").isdigit():
                used.add(int(p.text))
        n = 1
        while n in used:
            n += 1
        return str(n)

    def _next_numerical_id(self) -> int:
        used = set()
        for el in self.tree.root.iter():
            id_attr = el.get("id", "")
            if id_attr.startswith("transition_") and id_attr[11:].isdigit():
                used.add(int(id_attr[11:]))
        n = 0
        while n in used:
            n += 1
        return n

    def _bump_tractor_duration(self) -> None:
        t = self.tree.get_tractor()
        if t is None:
            return
        # Project duration = max out of any entry.
        max_out = 0.0
        for e in self.tree.root.iter("entry"):
            max_out = max(max_out, _tc_to_sec(e.get("out", "00:00:00.000")))
        t.set("out", _sec_to_tc(max_out))

    def _touch_modified(self) -> None:
        from datetime import datetime, timezone
        from .io import _sec_to_tc
        bin_el = self.tree.get_main_bin()
        if bin_el is None:
            return
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        for p in bin_el.iter("property"):
            if p.get("name") == "kdenlive:docproperties.modified":
                p.text = now
                return

    def _producer_has_audio(self, producer: etree._Element) -> bool:
        clip_type = None
        for p in producer.findall("property"):
            if p.get("name") == "kdenlive:clip_type":
                clip_type = p.text
                break
        if clip_type is not None:
            if clip_type in ("2", "5", "6"):
                return False
        
        svc = producer.find("property[@name='mlt_service']")
        if svc is not None and svc.text in ("color", "qimage", "blip"):
            return False
        
        return True

    def _is_audio_track(self, track_index: int) -> bool:
        tracks = self.tree.get_tracks()
        if track_index < 0 or track_index >= len(tracks):
            return False
        tractor = tracks[track_index]
        at = tractor.find("property[@name='kdenlive:audio_track']")
        return at is not None and at.text == "1"

    def _get_paired_track_index(self, track_index: int) -> int | None:
        tracks = self.tree.get_tracks()
        video_indices = []
        audio_indices = []
        for i, tr in enumerate(tracks):
            at = tr.find("property[@name='kdenlive:audio_track']")
            if at is not None and at.text == "1":
                audio_indices.append(i)
            else:
                video_indices.append(i)
        
        if track_index in video_indices:
            idx = video_indices.index(track_index)
            if idx < len(audio_indices):
                return audio_indices[idx]
        elif track_index in audio_indices:
            idx = audio_indices.index(track_index)
            if idx < len(video_indices):
                return video_indices[idx]
        return None

    def _find_all_entries(self, clip_id: str) -> list[tuple[etree._Element, int]]:
        results = []
        for i, tr in enumerate(self.tree.get_tracks()):
            for pl in self.tree.get_track_playlists(tr):
                for entry in pl.iter("entry"):
                    for p in entry.iter("property"):
                        if p.get("name") == "kdenlive:id" and p.text == clip_id:
                            results.append((entry, i))
        return results


# --- Private helpers ---------------------------------------------------------


def _entry_to_clip_summary(
    entry: etree._Element,
    track_index: int,
    playlist: etree._Element,
    tree: ProjectTree,
) -> ClipSummary:
    kid = ""
    for p in entry.iter("property"):
        if p.get("name") == "kdenlive:id":
            kid = p.text or ""
            break
    prod_id = entry.get("producer", "")
    source_path = ""
    source_name = ""
    source_kid = ""  # bin producer's kdenlive:id — the value to pass as source_id
    for prod in tree.root.iter("producer"):
        if prod.get("id") == prod_id:
            for p in prod.iter("property"):
                if p.get("name") == "resource":
                    source_path = p.text or ""
                    source_name = Path(source_path).name
                elif p.get("name") == "kdenlive:id":
                    source_kid = p.text or ""
            break
    effects: list[str] = []
    for f in entry.iter("filter"):
        for p in f.iter("property"):
            if p.get("name") == "kdenlive_id":
                effects.append(p.text or "")
                break  # one label per filter
    start = _entry_start_sec(playlist, entry)
    in_val = _tc_to_sec(entry.get("in", "00:00:00.000"))
    out_val = _tc_to_sec(entry.get("out", "00:00:00.000"))
    duration = out_val - in_val
    return ClipSummary(
        clip_id=kid,
        track_index=track_index,
        start_sec=start,
        end_sec=start + duration,
        source_id=source_kid,
        source_path=source_path,
        source_name=source_name,
        source_in_sec=in_val,
        source_out_sec=out_val,
        effects=tuple(effects),
    )


def _transition_to_summary(
    tr: etree._Element, track_index: int, playlist: etree._Element
) -> TransitionSummary:
    kid = ""
    for p in tr.iter("property"):
        if p.get("name") == "kdenlive:id":
            kid = p.text or ""
            break
    mlt = ""
    for p in tr.iter("property"):
        if p.get("name") == "mlt_service":
            mlt = p.text or ""
            break
    return TransitionSummary(
        transition_id=kid,
        track_index=track_index,
        start_sec=_tc_to_sec(tr.get("in", "00:00:00.000")),
        end_sec=_tc_to_sec(tr.get("out", "00:00:00.000")),
        kind=mlt or tr.get("id", "transition"),
    )


def _iter_markers(tree: ProjectTree) -> Iterable[MarkerSummary]:
    for m in tree.root.iter("marker"):
        time = 0.0
        label = ""
        kind = "marker"
        for p in m.iter("property"):
            if p.get("name") == "time":
                time = _tc_to_sec(p.text or "00:00:00.000")
            elif p.get("name") == "comment":
                label = p.text or ""
            elif p.get("name") == "type":
                kind = {0: "marker", 1: "guide", 2: "chapter"}.get(
                    int(p.text or 0), "marker"
                )
        yield MarkerSummary(position_sec=time, label=label, kind=kind)
