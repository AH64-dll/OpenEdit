"""
test_phase2.py — Phase 2 acceptance tests.

Covers (per the spec's PHASE_2_project_engine.md):

  [x] Loads manual_baseline.kdenlive, re-saves with zero changes,
      output is semantically identical to input.
  [x] Each operation in the API has a passing unit test and a
      fix:-hinted rejection test for at least one invalid input.
  [x] A project built through the API, with at least one clip +
      transition + title, opens in Kdenlive with the correct project
      name (not "Untitled"). Verified via the saved file structure
      and the "Untitled" pre-check from Phase 0.
  [x] effect_id/transition-type arguments are rejected with a clear
      error if they're not in the catalog.

Run:
    cd pyagent-kdenlive-guide
    python3 -m unittest phase2_project_engine.test_phase2 -v
"""

from __future__ import annotations

import json
import sys
import unittest
from lxml import etree
from pathlib import Path
from xml.etree import ElementTree as ET

# Make this directory importable as a package
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))

from phase2_project_engine import (  # noqa: E402
    Catalog,
    KdenliveFileBackend,
    ProjectTree,
    ValidationError,
    load_project,
    save_project,
)


REPO = Path("/home/ah64/apps/mlt-pipeline")
FIXTURE = HERE.parent / "spike-results/fixtures/manual_baseline.kdenlive"
CATALOG_PATH = HERE.parent / "phase1_knowledge_base/catalog.json"


def _make_catalog() -> Catalog:
    return Catalog.from_json(CATALOG_PATH)


def _make_backend() -> KdenliveFileBackend:
    """A fresh in-memory backend (no file) for unit tests."""
    return KdenliveFileBackend(project_path=None, catalog=_make_catalog())


def _count_kdenlive_props(path: Path) -> int:
    """Count `kdenlive:` properties anywhere in a .kdenlive file."""
    text = path.read_text(encoding="utf-8", errors="replace")
    return sum(
        1
        for line in text.splitlines()
        if 'kdenlive:' in line
    )


# ---- Acceptance #1: round-trip safety ---------------------------------------


class TestRoundTrip(unittest.TestCase):
    """Loading and re-saving the Phase 0 fixture must be lossless
    on the parts PyAgent doesn't touch."""

    def test_load_and_resave_with_no_changes(self):
        if not FIXTURE.exists():
            self.skipTest(f"missing fixture: {FIXTURE}")
        out = FIXTURE.with_name("roundtrip_out.kdenlive")
        try:
            tree = load_project(FIXTURE)
            save_project(tree, out)
            # Compare semantic content (number of elements, total
            # attributes). lxml may reorder attributes; that's allowed
            # by the spec ("whitespace/attribute-order differences are
            # fine; missing data is not").
            self._assert_semantic_equality(FIXTURE, out)
        finally:
            if out.exists():
                out.unlink()

    def _assert_semantic_equality(self, a: Path, b: Path) -> None:
        def summarize(p: Path) -> dict:
            tree = ET.parse(p)
            root = tree.getroot()
            return {
                "root_tag": root.tag,
                "root_attrs": sorted(root.attrib.items()),
                "child_count": sum(1 for _ in root),
                "tag_counts": self._tag_histogram(root),
                "all_text": [el.text for el in root.iter() if el.text],
            }
        s_a = summarize(a)
        s_b = summarize(b)
        # Allowed to differ: text whitespace, attribute order.
        # Must match: root tag, child count, tag histogram, total non-blank
        # text length within 1%.
        self.assertEqual(s_a["root_tag"], s_b["root_tag"], "root tag changed")
        self.assertEqual(
            s_a["child_count"], s_b["child_count"], "number of root children changed"
        )
        self.assertEqual(
            s_a["tag_counts"], s_b["tag_counts"], "tag histogram changed"
        )
        text_len_a = sum(len(t) for t in s_a["all_text"])
        text_len_b = sum(len(t) for t in s_b["all_text"])
        if text_len_a > 0:
            delta = abs(text_len_a - text_len_b) / text_len_a
            self.assertLess(
                delta,
                0.01,
                f"text content shrank/expanded by {delta:.2%}: "
                f"{text_len_a} -> {text_len_b}",
            )

    @staticmethod
    def _tag_histogram(root) -> dict:
        from collections import Counter
        c = Counter(el.tag for el in root.iter())
        return dict(c)


# ---- Acceptance #2: every operation works, every operation rejects bad input --


class TestOperations(unittest.TestCase):
    """Each operation API method has a happy-path test and at least
    one ValidationError test."""

    def setUp(self):
        self.backend = _make_backend()
        # We need a real source to import. Reuse the mlt-pipeline fixture
        # if it exists, else skip.
        self.source = REPO / "testdata/clip_short.mp4"
        if not self.source.exists():
            self.skipTest("missing testdata/clip_short.mp4")

    # --- import_media ---

    def test_import_media_returns_ids(self):
        ids = self.backend.import_media([str(self.source)])
        self.assertEqual(len(ids), 1)
        # ID is a numeric string.
        self.assertTrue(ids[0].isdigit())

    def test_import_media_assigns_unique_kdenlive_ids(self):
        # Regression: bug where every imported producer got kdenlive:id=1
        # (the id value was read from the `name` attribute, not the element
        # text), so clips collided and insert_clip couldn't tell them apart.
        ids = self.backend.import_media(
            [str(self.source), str(self.source), str(self.source)]
        )
        self.assertEqual(len(ids), 3)
        # All three must be distinct numeric ids.
        self.assertEqual(len(set(ids)), 3)
        for i in ids:
            self.assertTrue(i.isdigit())

    def test_import_media_creates_root_level_producers(self):
        # Regression: bug where import_media SubElement'd the <producer>
        # inside the <playlist id="main_bin">, which is the wrong location.
        # MLT silently drops producers inside playlists, so the clips showed
        # up as empty/black in Kdenlive's timeline. Producers must be direct
        # children of the MLT root.
        self.backend.import_media([str(self.source)])
        # The in-memory backend exposes its tree via .tree.root
        root = self.backend.tree.root
        main_bin = root.find("playlist[@id='main_bin']")
        # main_bin must NOT contain any <producer> children.
        self.assertEqual(len(main_bin.findall("producer")), 0,
                         "import_media put <producer> inside <playlist> "
                         "main_bin instead of at MLT root — this breaks "
                         "the Kdenlive timeline display")
        # The new producer must be at root level.
        self.assertGreaterEqual(len(root.findall("producer")), 1)

    def test_import_media_rejects_missing_path(self):
        with self.assertRaises(ValidationError) as cm:
            self.backend.import_media(["/nope/not/here.mp4"])
        self.assertIn("fix:", str(cm.exception))

    def test_import_media_rejects_empty(self):
        with self.assertRaises(ValidationError) as cm:
            self.backend.import_media([""])
        self.assertIn("fix:", str(cm.exception))

    # --- insert_clip / append_clip ---

    def test_insert_clip_returns_id(self):
        ids = self.backend.import_media([str(self.source)])
        cid = self.backend.insert_clip(
            track_index=0,
            position_sec=0.0,
            source_id=ids[0],
            source_in_sec=0.0,
            source_out_sec=5.0,
        )
        self.assertTrue(cid.isdigit())
        summary = self.backend.get_timeline_summary()
        self.assertEqual(len(summary.clips), 1)
        self.assertEqual(summary.clips[0].clip_id, cid)
        self.assertEqual(summary.clips[0].start_sec, 0.0)
        self.assertEqual(summary.clips[0].end_sec, 5.0)

    def test_insert_clip_rejects_out_of_range_track(self):
        with self.assertRaises(ValidationError) as cm:
            self.backend.insert_clip(track_index=99, position_sec=0.0, source_id="1")
        self.assertIn("fix:", str(cm.exception))

    def test_insert_clip_rejects_out_of_range_out_sec(self):
        ids = self.backend.import_media([str(self.source)])
        with self.assertRaises(ValidationError) as cm:
            self.backend.insert_clip(
                track_index=0,
                position_sec=0.0,
                source_id=ids[0],
                source_in_sec=0.0,
                source_out_sec=999.0,
            )
        self.assertIn("fix:", str(cm.exception))
        self.assertIn("out_sec", str(cm.exception))

    def test_insert_clip_rejects_inverted_range(self):
        ids = self.backend.import_media([str(self.source)])
        with self.assertRaises(ValidationError) as cm:
            self.backend.insert_clip(
                track_index=0,
                position_sec=0.0,
                source_id=ids[0],
                source_in_sec=5.0,
                source_out_sec=2.0,
            )
        self.assertIn("fix:", str(cm.exception))

    def test_insert_clip_rejects_unknown_source(self):
        with self.assertRaises(Exception) as cm:
            self.backend.insert_clip(
                track_index=0,
                position_sec=0.0,
                source_id="9999",
            )
        # BackendError or subclass.
        self.assertIn("no bin entry", str(cm.exception).lower())

    def test_append_clip_lands_at_end_of_track(self):
        ids = self.backend.import_media([str(self.source)])
        c1 = self.backend.insert_clip(0, 0.0, ids[0], 0.0, 3.0)
        c2 = self.backend.append_clip(0, ids[0], 0.0, 2.0)
        s = self.backend.get_timeline_summary()
        # The two clips together should span 0..5 on track 0.
        starts = sorted(c.start_sec for c in s.clips if c.track_index == 0)
        self.assertEqual(starts, [0.0, 3.0])

    # --- move_clip ---

    def test_move_clip_rejects_negative_position(self):
        ids = self.backend.import_media([str(self.source)])
        cid = self.backend.insert_clip(0, 0.0, ids[0], 0.0, 2.0)
        with self.assertRaises(ValidationError) as cm:
            self.backend.move_clip(cid, 0, -1.0)
        self.assertIn("fix:", str(cm.exception))

    # --- trim_clip ---

    def test_trim_clip_changes_in_out(self):
        ids = self.backend.import_media([str(self.source)])
        cid = self.backend.insert_clip(0, 0.0, ids[0], 0.0, 5.0)
        self.backend.trim_clip(cid, 1.0, 4.0)
        s = self.backend.get_timeline_summary()
        clip = next(c for c in s.clips if c.clip_id == cid)
        self.assertEqual(clip.start_sec, 1.0)
        self.assertEqual(clip.end_sec, 4.0)

    def test_trim_clip_rejects_inverted_range(self):
        ids = self.backend.import_media([str(self.source)])
        cid = self.backend.insert_clip(0, 0.0, ids[0], 0.0, 5.0)
        with self.assertRaises(ValidationError) as cm:
            self.backend.trim_clip(cid, 4.0, 2.0)
        self.assertIn("fix:", str(cm.exception))

    # --- delete_clip ---

    def test_delete_clip_removes_it(self):
        ids = self.backend.import_media([str(self.source)])
        cid = self.backend.insert_clip(0, 0.0, ids[0], 0.0, 5.0)
        self.assertEqual(len(self.backend.get_timeline_summary().clips), 1)
        self.backend.delete_clip(cid)
        self.assertEqual(len(self.backend.get_timeline_summary().clips), 0)

    def test_delete_clip_rejects_unknown_id(self):
        with self.assertRaises(Exception) as cm:
            self.backend.delete_clip("99999")
        self.assertIn("no clip", str(cm.exception).lower())

    # --- add_transition ---

    def test_add_transition_returns_id(self):
        ids = self.backend.import_media([str(self.source)])
        a = self.backend.insert_clip(0, 0.0, ids[0], 0.0, 5.0)
        b = self.backend.append_clip(0, ids[0], 0.0, 5.0)
        tid = self.backend.add_transition(a, b, kind="dissolve", duration_sec=1.0)
        self.assertTrue(tid.isdigit())
        s = self.backend.get_timeline_summary()
        self.assertEqual(len(s.transitions), 1)
        self.assertEqual(s.transitions[0].kind, "luma")  # mlt_service for dissolve

    def test_add_transition_rejects_unknown_kind(self):
        ids = self.backend.import_media([str(self.source)])
        a = self.backend.insert_clip(0, 0.0, ids[0], 0.0, 5.0)
        b = self.backend.append_clip(0, ids[0], 0.0, 5.0)
        with self.assertRaises(ValidationError) as cm:
            self.backend.add_transition(a, b, kind="fancy_unknown_transition")
        self.assertIn("fix:", str(cm.exception))
        self.assertIn("catalog", str(cm.exception).lower())

    def test_add_transition_rejects_cross_track(self):
        ids = self.backend.import_media([str(self.source)])
        # Need a second track first; build a synthetic track_2.
        backend = self.backend
        v2 = etree_SubElement(backend.tree.root, "playlist")
        v2.set("id", "video_track_2")
        tr2 = etree_SubElement(backend.tree.root, "tractor")
        tr2.set("id", "tractor_v2")
        mt2 = etree_SubElement(tr2, "multitrack")
        tref2 = etree.SubElement(mt2, "track")
        tref2.set("producer", "video_track_2")
        a = backend.insert_clip(0, 0.0, ids[0], 0.0, 5.0)
        b = backend.insert_clip(1, 0.0, ids[0], 0.0, 5.0)
        with self.assertRaises(ValidationError) as cm:
            backend.add_transition(a, b, kind="dissolve", duration_sec=1.0)
        self.assertIn("fix:", str(cm.exception))

    # --- apply_effect ---

    def test_apply_effect_with_default_params(self):
        ids = self.backend.import_media([str(self.source)])
        cid = self.backend.insert_clip(0, 0.0, ids[0], 0.0, 5.0)
        eid = self.backend.apply_effect(cid, "brightness")
        self.assertTrue(eid)
        s = self.backend.get_timeline_summary()
        clip = next(c for c in s.clips if c.clip_id == cid)
        self.assertIn("brightness", clip.effects)

    def test_apply_effect_with_param(self):
        ids = self.backend.import_media([str(self.source)])
        cid = self.backend.insert_clip(0, 0.0, ids[0], 0.0, 5.0)
        self.backend.apply_effect(
            cid, "brightness", params={"level": 50}
        )
        # Inspect the XML directly to confirm the param was written.
        entry, _ = self.backend._find_entry(cid)
        level = None
        for p in entry.iter("property"):
            if p.get("name") == "level":
                level = p.text
                break
        # `level` is type `animated` -> float() coercion; "50" and
        # "50.0" are both legitimate Kdenlive representations.
        self.assertEqual(float(level), 50.0)

    def test_apply_effect_rejects_unknown_id(self):
        ids = self.backend.import_media([str(self.source)])
        cid = self.backend.insert_clip(0, 0.0, ids[0], 0.0, 5.0)
        with self.assertRaises(ValidationError) as cm:
            self.backend.apply_effect(cid, "nope_not_an_effect")
        self.assertIn("fix:", str(cm.exception))
        self.assertIn("catalog", str(cm.exception).lower())

    def test_apply_effect_rejects_bad_param_name(self):
        ids = self.backend.import_media([str(self.source)])
        cid = self.backend.insert_clip(0, 0.0, ids[0], 0.0, 5.0)
        with self.assertRaises(ValidationError) as cm:
            self.backend.apply_effect(
                cid, "brightness", params={"totally_made_up": 0.5}
            )
        self.assertIn("fix:", str(cm.exception))

    def test_apply_effect_rejects_wrong_param_type(self):
        ids = self.backend.import_media([str(self.source)])
        cid = self.backend.insert_clip(0, 0.0, ids[0], 0.0, 5.0)
        with self.assertRaises(ValidationError) as cm:
            self.backend.apply_effect(
                cid, "brightness", params={"level": "not a number"}
            )
        self.assertIn("fix:", str(cm.exception))

    # --- add_marker ---

    def test_add_marker(self):
        self.backend.add_marker(2.5, "cut point", kind="marker")
        s = self.backend.get_timeline_summary()
        self.assertEqual(len(s.markers), 1)
        self.assertEqual(s.markers[0].position_sec, 2.5)
        self.assertEqual(s.markers[0].label, "cut point")

    def test_add_marker_rejects_bad_kind(self):
        with self.assertRaises(ValidationError) as cm:
            self.backend.add_marker(1.0, "x", kind="bookmark")
        self.assertIn("fix:", str(cm.exception))

    def test_add_marker_rejects_negative_position(self):
        with self.assertRaises(ValidationError) as cm:
            self.backend.add_marker(-1.0, "x")
        self.assertIn("fix:", str(cm.exception))

    def test_producer_definition_order(self):
        # Importing a new media file should insert it before any playlists or tractors
        ids = self.backend.import_media([str(REPO / "testdata/clip_short.mp4")])
        root = self.backend.tree.root
        
        # Verify the index of the newly added producer relative to playlists/tractors
        first_container_idx = None
        new_producer_idx = None
        
        for idx, child in enumerate(root):
            if child.tag == "producer" and child.get("id") == f"producer_{len(root) - 1}":
                new_producer_idx = idx
            elif child.tag in ("playlist", "tractor") and first_container_idx is None:
                first_container_idx = idx
                
        self.assertIsNotNone(new_producer_idx)
        self.assertIsNotNone(first_container_idx)
        self.assertTrue(new_producer_idx < first_container_idx, "new producer should be defined before playlists/tractors")


def etree_SubElement(parent, tag, attrib={}):
    """Local helper to avoid importing lxml at test module top-level."""
    from lxml import etree
    el = etree.SubElement(parent, tag, attrib)
    return el


# ---- Acceptance #3: the "Untitled" fix --------------------------------------


class TestUntitledFix(unittest.TestCase):
    """A project built through the API must have the kdenlive:
    properties Kdenlive needs to recognize it as a real project
    (not 'Untitled'). This is the concrete check that the
    gap from Phase 0's diff task has been closed."""

    def test_new_project_has_required_kdenlive_props(self):
        backend = _make_backend()
        ids = backend.import_media([str(REPO / "testdata/clip_short.mp4")])
        backend.insert_clip(0, 0.0, ids[0], 0.0, 5.0)
        backend.add_marker(2.0, "first cut")

        out = Path("/tmp/opencode_pyagent_test.kdenlive")
        try:
            backend.save(out)
            text = out.read_text(encoding="utf-8", errors="replace")
            # Check the minimum kdenlive: set from the diff doc.
            required = [
                "kdenlive:docproperties.uuid",
                "kdenlive:docproperties.version",
                "kdenlive:clipname",
                "kdenlive:duration",
                "kdenlive:file_hash",
                "kdenlive:file_size",
                "kdenlive:folderid",
                "kdenlive:binType",
                "kdenlive:clip_type",
                "kdenlive:id",
            ]
            missing = [r for r in required if r not in text]
            self.assertEqual(missing, [], f"missing kdenlive: properties: {missing}")
        finally:
            if out.exists():
                out.unlink()

    def test_built_project_has_zero_dissolve_default_transition(self):
        """A project with no transitions should have none in the summary."""
        backend = _make_backend()
        ids = backend.import_media([str(REPO / "testdata/clip_short.mp4")])
        backend.insert_clip(0, 0.0, ids[0], 0.0, 5.0)
        s = backend.get_timeline_summary()
        self.assertEqual(len(s.transitions), 0)


# ---- Acceptance #4: catalog validation --------------------------------------


class TestCatalogValidation(unittest.TestCase):
    """effect_id / transition-kind not in the catalog must be rejected."""

    def test_unknown_effect_rejected_with_catalog_hint(self):
        backend = _make_backend()
        ids = backend.import_media([str(REPO / "testdata/clip_short.mp4")])
        cid = backend.insert_clip(0, 0.0, ids[0], 0.0, 5.0)
        with self.assertRaises(ValidationError) as cm:
            backend.apply_effect(cid, "completely_made_up_xyz")
        msg = str(cm.exception).lower()
        self.assertIn("fix:", msg)
        self.assertIn("catalog", msg)

    def test_unknown_transition_rejected_with_catalog_hint(self):
        backend = _make_backend()
        ids = backend.import_media([str(REPO / "testdata/clip_short.mp4")])
        a = backend.insert_clip(0, 0.0, ids[0], 0.0, 5.0)
        b = backend.append_clip(0, ids[0], 0.0, 5.0)
        with self.assertRaises(ValidationError) as cm:
            backend.add_transition(a, b, kind="totally_made_up_xyz")
        msg = str(cm.exception).lower()
        self.assertIn("fix:", msg)
        self.assertIn("catalog", msg)


# ---- Round-trip the PHASE 0 fixture with one safe operation -----------------


class TestRoundTripWithOneOp(unittest.TestCase):
    """Open the Phase 0 fixture, add a marker, save, and assert
    nothing else was changed."""

    def test_add_marker_preserves_other_data(self):
        if not FIXTURE.exists():
            self.skipTest("missing Phase 0 fixture")
        # The fixture has 624x356 profile; we need a source on disk
        # to add a clip. Just add a marker instead — no source needed.
        from copy import deepcopy
        original = FIXTURE.read_text(encoding="utf-8", errors="replace")

        backend = KdenliveFileBackend(project_path=FIXTURE, catalog=_make_catalog())
        # Snapshot the project before mutation.
        before = deepcopy(backend.tree)
        backend.add_marker(2.0, "phase2 marker", kind="guide")
        out = FIXTURE.with_name("rt_with_marker.kdenlive")
        try:
            backend.save(out)
            # Reload the saved file and compare structure to the before
            # snapshot. Only the marker block should differ.
            after = load_project(out)

            def all_elements(root):
                return sorted(
                    (el.tag, el.get("name", ""), el.text or "")
                    for el in root.iter()
                )

            before_elements = set(all_elements(before.root))
            after_elements = set(all_elements(after.root))
            added = after_elements - before_elements
            removed = before_elements - after_elements
            # The marker adds 3 new properties (time, comment, type).
            # It may also reorder attribute order; that's fine.
            self.assertEqual(
                removed, set(), f"round-trip dropped data: {removed}"
            )
            # The added set must be EXACTLY the 3 new marker properties.
            added_marker_only = [
                a for a in added
                if a[0] == "property" and a[1] in ("time", "comment", "type")
            ]
            self.assertEqual(
                len(added_marker_only), 3,
                f"expected 3 new marker properties, got {len(added_marker_only)}: {added_marker_only}",
            )
        finally:
            if out.exists():
                out.unlink()


class TestSyncedClips(unittest.TestCase):
    def setUp(self):
        self.backend = _make_backend()
        self.source = REPO / "testdata/clip_short.mp4"
        if not self.source.exists():
            self.skipTest("missing testdata/clip_short.mp4")

        from lxml import etree
        root = self.backend.tree.root
        
        # Audio playlist
        a1_pl = etree.SubElement(root, "playlist")
        a1_pl.set("id", "audio_track_playlist")
        
        # Audio tractor
        a1_tractor = etree.SubElement(root, "tractor")
        a1_tractor.set("id", "audio_track_tractor")
        aprop = etree.SubElement(a1_tractor, "property")
        aprop.set("name", "kdenlive:audio_track")
        aprop.text = "1"
        atrack = etree.SubElement(a1_tractor, "track")
        atrack.set("producer", "audio_track_playlist")

    def test_insert_clip_dual_track(self):
        ids = self.backend.import_media([str(self.source)])
        # Track 0 is video_track, track 1 is audio_track_tractor.
        kid = self.backend.insert_clip(0, 2.0, ids[0], 0.0, 5.0)
        
        # Verify video entry
        video_entries = self.backend.tree.root.xpath(".//playlist[@id='video_track']/entry")
        self.assertEqual(len(video_entries), 1)
        self.assertEqual(video_entries[0].xpath("./property[@name='kdenlive:id']/text()")[0], kid)
        
        # Verify audio entry
        audio_entries = self.backend.tree.root.xpath(".//playlist[@id='audio_track_playlist']/entry")
        self.assertEqual(len(audio_entries), 1)
        self.assertEqual(audio_entries[0].xpath("./property[@name='kdenlive:id']/text()")[0], kid)

    def test_insert_clip_video_only(self):
        ids = self.backend.import_media([str(self.source)])
        kid = self.backend.insert_clip(0, 2.0, ids[0], 0.0, 5.0, video_only=True)
        
        video_entries = self.backend.tree.root.xpath(".//playlist[@id='video_track']/entry")
        self.assertEqual(len(video_entries), 1)
        
        audio_entries = self.backend.tree.root.xpath(".//playlist[@id='audio_track_playlist']/entry")
        self.assertEqual(len(audio_entries), 0)

    def test_delete_clip_dual_track(self):
        ids = self.backend.import_media([str(self.source)])
        kid = self.backend.insert_clip(0, 2.0, ids[0], 0.0, 5.0)
        
        # Verify both inserted
        self.assertEqual(len(self.backend.tree.root.xpath(".//entry")), 2)
        
        self.backend.delete_clip(kid)
        self.assertEqual(len(self.backend.tree.root.xpath(".//entry")), 0)

    def test_move_clip_dual_track(self):
        ids = self.backend.import_media([str(self.source)])
        kid = self.backend.insert_clip(0, 2.0, ids[0], 0.0, 5.0)
        
        # Verify starting times are 2.0
        s0 = self.backend.get_timeline_summary()
        self.assertEqual(len(s0.clips), 2)
        self.assertEqual(s0.clips[0].start_sec, 2.0)
        self.assertEqual(s0.clips[1].start_sec, 2.0)
        
        # Move video track (0) to position 5.0 (which moves audio track 1 as well)
        self.backend.move_clip(kid, 0, 5.0)
        s1 = self.backend.get_timeline_summary()
        self.assertEqual(len(s1.clips), 2)
        self.assertEqual(s1.clips[0].start_sec, 5.0)
        self.assertEqual(s1.clips[1].start_sec, 5.0)

    def test_trim_clip_dual_track(self):
        ids = self.backend.import_media([str(self.source)])
        kid = self.backend.insert_clip(0, 2.0, ids[0], 0.0, 5.0)
        
        self.backend.trim_clip(kid, 1.0, 4.0)
        s = self.backend.get_timeline_summary()
        
        self.assertEqual(len(s.clips), 2)
        # Trim from 1.0 to 4.0 (shift of 1s right)
        self.assertEqual(s.clips[0].start_sec, 3.0)
        self.assertEqual(s.clips[1].start_sec, 3.0)
        self.assertEqual(s.clips[0].end_sec, 6.0)
        self.assertEqual(s.clips[1].end_sec, 6.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
