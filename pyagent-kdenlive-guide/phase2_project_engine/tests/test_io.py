"""Tests for phase2_project_engine.io — ProjectTree + load/save + timecode helpers."""
import os
import pytest
from lxml import etree
from phase2_project_engine.io import (
    ProjectTree, load_project, save_project, _sec_to_tc, _tc_to_sec,
)


def test_sec_to_tc_roundtrip():
    for sec, tc in [(0.0, "00:00:00.000"), (1.5, "00:00:01.500"),
                     (3661.123, "01:01:01.123")]:
        assert _sec_to_tc(sec) == tc
        assert abs(_tc_to_sec(tc) - sec) < 1e-6


def test_load_save_roundtrip(tmp_path):
    p = tmp_path / "x.kdenlive"
    p.write_text("""<?xml version="1.0"?>
<mlt version="7.40.0" producer="main_bin" LC_NUMERIC="C">
  <profile width="1920" height="1080" frame_rate_num="30"/>
  <playlist id="main_bin"/>
</mlt>
""")
    tree = load_project(p)
    save_project(tree, p)
    tree2 = load_project(p)
    # Project-level attrs survive
    assert tree2.root.get("version") == "7.40.0"
    assert tree2.root.get("producer") == "main_bin"


def test_ensure_docproperties_idempotent(tmp_path):
    p = tmp_path / "x.kdenlive"
    p.write_text('<mlt><profile/><playlist id="main_bin"/></mlt>')
    tree = load_project(p)
    tree.ensure_docproperties()
    tree.ensure_docproperties()  # second call must not duplicate
    bin_el = tree.get_main_bin()
    seen = [pp.get("name") for pp in bin_el.iter("property")]
    assert seen.count("kdenlive:docproperties.uuid") == 1
