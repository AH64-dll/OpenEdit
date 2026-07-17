"""Tests for catalog_slice.build_catalog_slice."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

# Allow the test to be run with either `python3 -m unittest test_catalog_slice`
# (cwd on sys.path) or `python3 -m unittest phase3_pyagent_core.test_catalog_slice`
# (package-qualified). The try/except falls back gracefully.
try:
    from phase3_pyagent_core.catalog_slice import build_catalog_slice
except ImportError:
    from catalog_slice import build_catalog_slice  # type: ignore[no-redef]


SAMPLE_CATALOG = {
    "effects": [
        {"id": "brightness", "name": "Brightness", "tag": "brightness",
         "description": "Adjust clip brightness."},
        {"id": "crop", "name": "Crop", "tag": "crop",
         "description": "Crop the edges."},
        # No name -> should be excluded.
        {"id": "broken", "tag": "broken"},
    ],
    "transitions": [
        {"id": "dissolve", "name": "Dissolve", "tag": "luma",
         "description": "Crossfade between two clips."},
    ],
    "generators": [],
    "metadata_stuff_we_skip": "ignore me",
}


class TestBuildSlice(unittest.TestCase):
    def test_includes_named_entries(self):
        slice_text = build_catalog_slice(SAMPLE_CATALOG)
        self.assertIn("brightness", slice_text)
        self.assertIn("Brightness", slice_text)
        self.assertIn("Crop", slice_text)
        self.assertIn("Dissolve", slice_text)

    def test_excludes_unnamed_entries(self):
        slice_text = build_catalog_slice(SAMPLE_CATALOG)
        self.assertNotIn("broken", slice_text)

    def test_one_line_per_entry(self):
        slice_text = build_catalog_slice(SAMPLE_CATALOG)
        # 3 named entries: brightness, crop, dissolve.
        self.assertEqual(len([l for l in slice_text.splitlines() if l.strip()]), 3)

    def test_format_includes_id_name_tag(self):
        slice_text = build_catalog_slice(SAMPLE_CATALOG)
        # Format: "{tag} | {id} | {name} | {description}"
        for line in slice_text.splitlines():
            parts = [p.strip() for p in line.split("|")]
            self.assertEqual(len(parts), 4)

    def test_filter_by_kind(self):
        slice_text = build_catalog_slice(SAMPLE_CATALOG, kinds=("effects",))
        self.assertIn("Brightness", slice_text)
        self.assertNotIn("Dissolve", slice_text)

    def test_accepts_path_string(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "cat.json"
            p.write_text(json.dumps(SAMPLE_CATALOG))
            slice_text = build_catalog_slice(str(p))
            self.assertIn("Brightness", slice_text)


if __name__ == "__main__":
    unittest.main()
