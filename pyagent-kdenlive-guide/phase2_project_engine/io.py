"""io.py — low-level XML I/O for .kdenlive files.

Round-trip safety (Phase 2 acceptance criterion #1: load a .kdenlive,
re-save with zero changes, output is semantically identical) is the
load-bearing constraint. We never touch anything we don't have a reason
to modify; we parse with `remove_blank_text=False` so Kdenlive's
indentation survives.

`ProjectTree` is a thin wrapper around the lxml element tree that knows
Kdenlive's structural conventions (root, profile, main_bin, docprops).
Track-related logic lives in `tracks.py`.
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from lxml import etree


# --- Constants ---------------------------------------------------------------

MLT_VERSION = "7.40.0"
KdenliveDocVersion = "1.1"  # matches what 26.04 writes


# --- Timecode helpers --------------------------------------------------------


def _sec_to_tc(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    ms = int(round((sec - int(sec)) * 1000))
    if ms == 1000:
        ms = 0
        s += 1
    if s == 60:
        s = 0
        m += 1
    if m == 60:
        m = 0
        h += 1
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def _tc_to_sec(s: str) -> float:
    h, m, rest = s.split(":")
    sec, frac = rest.split(".")
    return int(h) * 3600 + int(m) * 60 + int(sec) + int(frac) / 1000.0


# --- ProjectTree -------------------------------------------------------------


@dataclass
class ProjectTree:
    """In-memory representation of a .kdenlive project.

    `root` is the lxml <mlt> element. Use the helper methods below
    rather than touching root directly; the helpers know the Kdenlive
    structural conventions (main_bin, docproperties, etc.)."""

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
    "_sec_to_tc",
    "_tc_to_sec",
]
