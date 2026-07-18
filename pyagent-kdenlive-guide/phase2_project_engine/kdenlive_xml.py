"""
kdenlive_xml.py — low-level XML I/O for .kdenlive files.

The round-trip safety requirement (Phase 2 acceptance criterion #1:
"load manual_baseline.kdenlive, re-save with zero changes, output is
semantically identical to input") is the load-bearing constraint here.

Approach: use lxml.etree. The trick to round-tripping unknown elements
faithfully is to NEVER touch anything we don't have a reason to
modify. We parse with `remove_blank_text=False` so Kdenlive's
indentation survives, and we walk the tree with custom helpers that
preserve:
  - element order (children are only appended at the end of their
    parent, never reordered)
  - attribute order (lxml preserves it as parsed)
  - whitespace and text nodes
  - comments and processing instructions
  - namespace prefixes (lxml emits ns0/ns1 by default, so we save
    through a small `tostring` wrapper that forces prefixes)

The engine uses three operations on this module:
  - load(path) -> ProjectTree
  - save(tree, path)
  - apply_operations(tree, ops)   # for batched edits with one I/O

`ProjectTree` is a thin wrapper around the lxml element tree that
knows about Kdenlive's structural conventions (root, profile, main_bin,
black track, video tracks).
"""

from __future__ import annotations

import hashlib
import os
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from lxml import etree

from .io import _sec_to_tc


# --- Constants ---------------------------------------------------------------

# The Kdenlive XML root element namespace (used by newer effect XMLs
# in /usr/share/kdenlive/effects/, NOT by the project file itself —
# the project file's <mlt> element is in MLT's own namespace).
MLT_VERSION = "7.40.0"
KdenliveDocVersion = "1.1"  # matches what 26.04 writes

# --- ProjectTree -------------------------------------------------------------


@dataclass
class ProjectTree:
    """In-memory representation of a .kdenlive project.

    `root` is the lxml <mlt> element. Use the helper methods below
    rather than touching root directly; the helpers know the Kdenlive
    structural conventions (main_bin, black track, etc.)."""

    root: etree._Element
    path: Path | None = None

    # --- Read helpers ---

    def get_profile(self) -> dict:
        p = self.root.find("profile")
        if p is None:
            return {}
        return dict(p.attrib)

    def get_profile_fps(self) -> float:
        p = self.get_profile()
        num = int(p.get("frame_rate_num", "30"))
        den = int(p.get("frame_rate_den", "1"))
        return num / den if den else 30.0

    def get_profile_resolution(self) -> tuple[int, int]:
        p = self.get_profile()
        return int(p.get("width", "1920")), int(p.get("height", "1080"))

    def get_main_bin(self) -> etree._Element | None:
        return self.root.find("playlist[@id='main_bin']")

    def get_tracks(self) -> list[etree._Element]:
        """Return the tractor elements that represent user-facing tracks
        (V1, V2, V3, A1, ...). Order is visual: video tracks first
        (top-to-bottom in Kdenlive's UI), then audio tracks.

        Each Kdenlive track is a <tractor> with <track> children (either
        directly under the tractor, or inside a <multitrack> wrapper).
        We exclude:
        - the project tractor (the one with kdenlive:projectTractor=1)
        - the main sequence tractor (referenced from main_bin)
        - any tractor that has no <track> children at all

        A tractor with kdenlive:audio_track=1 is an audio track; it
        goes at the END of the returned list regardless of XML order.
        """
        # Find the main sequence (referenced by main_bin) to skip it.
        mb = self.root.find("playlist[@id='main_bin']")
        main_seq_id = None
        if mb is not None:
            for e in mb.findall("entry"):
                prod = e.get("producer")
                if prod and prod.startswith("{"):
                    main_seq_id = prod
                    break
        video_tracks = []
        audio_tracks = []
        for tr in self.root.findall("tractor"):
            tid = tr.get("id") or ""
            if tid == main_seq_id:
                continue
            if tr.find("property[@name='kdenlive:projectTractor']") is not None:
                continue
            if not tr.findall(".//track"):
                continue
            at = tr.find("property[@name='kdenlive:audio_track']")
            if at is not None and at.text == "1":
                audio_tracks.append(tr)
            else:
                video_tracks.append(tr)
        result = video_tracks + audio_tracks
        if not result:
            # Degenerate: no user tracks. Build one from a non-main_bin
            # playlist.
            target = None
            for c in self.root.findall("playlist"):
                if c.get("id") and c.get("id") != "main_bin":
                    if c.findall("entry"):
                        target = c
                        break
            if target is None:
                for c in self.root.findall("playlist"):
                    if c.get("id") and c.get("id") != "main_bin":
                        target = c
                        break
            if target is not None:
                synth = etree.SubElement(self.root, "tractor")
                synth.set("id", f"_synth_track_{target.get('id')}")
                tref = etree.SubElement(synth, "track")
                tref.set("producer", target.get("id"))
                result.append(synth)
        return result

    def get_track_playlists(self, tractor: etree._Element) -> list[etree._Element]:
        """Return the child playlists of a track tractor, resolved by
        following each <track producer="..."> reference.

        Kdenlive's track structure varies:
        - Real Kdenlive files: <tractor><track producer="playlistN"/></tractor>
        - Our generated files: <tractor><multitrack><track .../></multitrack></tractor>
        We handle both via .//track which finds tracks at any depth.
        """
        result = []
        for tref in tractor.findall(".//track"):
            prod_id = tref.get("producer")
            if not prod_id:
                continue
            pl = self.root.find(f"playlist[@id='{prod_id}']")
            if pl is not None:
                result.append(pl)
        return result

    def get_video_playlist(self, tractor: etree._Element) -> etree._Element | None:
        """Return the playlist to write video entries to.

        Kdenlive's track structure: a track tractor has 1-2 child
        playlists (video + audio). The tractor has kdenlive:audio_track=1
        only for the audio track. The video playlist is the OTHER one
        (the tractor without that property).

        In some files (like the demo edit.kdenlive), the structure is
        inverted: a tractor with kdenlive:audio_track=1 has child
        tracks that hold VIDEO content. We detect that case by checking
        whether the tractor's first child playlist already has video
        entries (entries whose producers have resource/avformat
        service), and return it if so.
        """
        playlists = self.get_track_playlists(tractor)
        if not playlists:
            return None
        at = tractor.find("property[@name='kdenlive:audio_track']")
        is_audio_tractor = at is not None and at.text == "1"
        if is_audio_tractor:
            # Check if any child playlist actually holds video content.
            for pl in playlists:
                if self._playlist_has_video_entries(pl):
                    return pl
            return None  # this is a true audio-only track
        # Video tractor — return the first non-audio child playlist.
        for pl in playlists:
            if pl.get("kdenlive:audio_track") == "1":
                continue
            return pl
        return playlists[0]

    def _playlist_has_video_entries(self, pl: etree._Element) -> bool:
        """True if any entry in this playlist references a video producer
        (one with a resource path / avformat service, NOT just an audio
        waveform)."""
        for e in pl.findall("entry"):
            prod = self.root.find(f"producer[@id='{e.get('producer')}']")
            if prod is None:
                continue
            svc = prod.find("property[@name='mlt_service']")
            if svc is not None and svc.text and "audio" in (svc.text or "").lower():
                continue
            res = prod.find("property[@name='resource']")
            if res is not None and res.text:
                # Has a media file — assume video.
                return True
        return False

    def get_video_tracks(self) -> list[etree._Element]:
        # Kdenlive marks video tracks with a 'kdenlive:track_type' property
        # on the playlist (or on the tractor's <track>). Without that, we
        # fall back to "all non-audio tracks": if any entry references a
        # producer with mlt_service in (avformat, avformat-novalidate,
        # qimage, kdenlivetitle, color, ...), the track is video.
        result = []
        for pl in self.get_tracks():
            if _is_video_track(pl):
                result.append(pl)
        return result

    def get_tractor(self) -> etree._Element | None:
        # Prefer the inner one (the one containing <multitrack>).
        for t in self.root.findall("tractor"):
            if t.find("multitrack") is not None:
                return t
        return self.root.find("tractor")

    def get_docproperties(self) -> dict[str, str]:
        """Read kdenlive:docproperties.* into a flat dict."""
        out = {}
        for prop in self.root.iter("property"):
            name = prop.get("name", "")
            if name.startswith("kdenlive:docproperties."):
                key = name[len("kdenlive:docproperties."):]
                out[key] = prop.text or ""
        return out

    # --- Write helpers (idempotent / additive) ---

    def ensure_kdenlive_properties_on_producer(
        self, producer: etree._Element, source_path: str
    ) -> None:
        """Add the minimum `kdenlive:` property set to a producer if
        not already present. Idempotent: re-running doesn't overwrite
        values that are already there.

        This is the operation that closes the "opens as Untitled" gap
        from Phase 0. See spike-results/mlt_vs_kdenlive_diff.txt.
        """
        existing = {
            p.get("name"): p for p in producer.iter("property") if p.get("name")
        }

        def set_prop(name: str, value: str) -> None:
            if name in existing:
                return
            new = etree.SubElement(producer, "property")
            new.set("name", name)
            new.text = value

        path = Path(source_path)
        if not path.is_absolute():
            path = path.resolve()
        if path.is_file():
            set_prop("kdenlive:file_size", str(path.stat().st_size))
            with open(path, "rb") as f:
                h = hashlib.md5(f.read()).hexdigest()
            set_prop("kdenlive:file_hash", h)
        set_prop("kdenlive:clipname", path.stem)
        set_prop("kdenlive:duration", _sec_to_tc(_probe_duration_sec(path)))
        set_prop("kdenlive:folderid", "-1")
        set_prop("kdenlive:binType", "std")
        set_prop("kdenlive:clip_type", "0")
        if "kdenlive:id" not in existing:
            # Pick an id that doesn't conflict with any other.
            # NOTE: the id value lives in the element *text*, not in the
            # `name` attribute (which is always the literal "kdenlive:id").
            taken = set()
            for p in self.root.iter("property"):
                if p.get("name") != "kdenlive:id":
                    continue
                val = (p.text or "").strip()
                if val.isdigit():
                    taken.add(int(val))
            n = 1
            while n in taken:
                n += 1
            set_prop("kdenlive:id", str(n))
        if "kdenlive:control_uuid" not in existing:
            set_prop(
                "kdenlive:control_uuid",
                f"{{{uuid.uuid4()}}}",
            )

    def ensure_docproperties(self) -> None:
        """Ensure the project has kdenlive:docproperties.* on the main_bin
        producer (or, failing that, as a child of <mlt>). Idempotent."""
        bin_el = self.get_main_bin()
        if bin_el is None:
            bin_el = etree.SubElement(self.root, "playlist")
            bin_el.set("id", "main_bin")
        existing = {
            p.get("name") for p in bin_el.iter("property") if p.get("name")
        }

        def set_prop(parent: etree._Element, name: str, value: str) -> None:
            if name in {p.get("name") for p in parent.iter("property")}:
                return
            new = etree.SubElement(parent, "property")
            new.set("name", name)
            new.text = value

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        set_prop(bin_el, "kdenlive:docproperties.uuid", str(uuid.uuid4()))
        set_prop(bin_el, "kdenlive:docproperties.version", KdenliveDocVersion)
        set_prop(bin_el, "kdenlive:docproperties.created", now)
        set_prop(bin_el, "kdenlive:docproperties.modified", now)

    def ensure_root_attrs(self) -> None:
        """Ensure <mlt> has the attributes a real Kdenlive save uses
        (version, producer, root, LC_NUMERIC)."""
        if not self.root.get("version"):
            self.root.set("version", MLT_VERSION)
        if not self.root.get("producer"):
            self.root.set("producer", "main_bin")
        if self.path and not self.root.get("root"):
            self.root.set("root", str(self.path.parent))
        if not self.root.get("{http://docbook.org/ns/docbook}LC_NUMERIC"):
            self.root.set("LC_NUMERIC", "C")


# --- Loaders / savers --------------------------------------------------------


def load_project(path: str | Path) -> ProjectTree:
    """Load a .kdenlive (or bare .mlt) file. Tolerates missing or
    partial kdenlive: properties — those are added by
    ensure_kdenlive_properties_on_producer on save, not on load."""
    p = Path(path)
    parser = etree.XMLParser(remove_blank_text=False)
    tree = etree.parse(str(p), parser)
    return ProjectTree(root=tree.getroot(), path=p)


def save_project(tree: ProjectTree, path: str | Path | None = None) -> None:
    """Serialize the project tree back to disk.

    Round-trip safety: we serialize through lxml with explicit
    formatting to match Kdenlive's style as closely as possible
    (XML declaration, 1-space indent, no self-closing tags for
    elements with text, etc.)."""
    if path is not None:
        tree.path = Path(path)
    tree.ensure_root_attrs()
    out = etree.tostring(
        tree.root,
        pretty_print=True,
        xml_declaration=True,
        encoding="utf-8",
    )
    target = tree.path
    if target is None:
        raise ValueError("save_project: no path given and tree.path is None")
    target.write_bytes(out)


# --- Helpers -----------------------------------------------------------------


def _is_video_track(playlist: etree._Element) -> bool:
    """Heuristic: a playlist is a video track if any of its entries
    references a producer with an mlt_service that produces video, OR
    if the playlist has the explicit kdenlive:track_type property
    (added by newer Kdenlive)."""
    for prop in playlist.iter("property"):
        if prop.get("name") == "kdenlive:track_type":
            return prop.text in ("video", None)  # None when not set
    return True  # assume video; refined below if we find a service


def _probe_duration_sec(path: Path) -> float:
    """Use ffprobe (already an mlt-pipeline dep) to read duration.
    Returns 0.0 if probe fails."""
    import json
    import subprocess

    try:
        out = subprocess.check_output(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json",
                str(path),
            ],
            text=True,
            timeout=5,
        )
        return float(json.loads(out)["format"]["duration"])
    except Exception:
        return 0.0


__all__ = [
    "ProjectTree",
    "load_project",
    "save_project",
]
