"""Tests for phase2_project_engine.ops._helpers — playlist navigation primitives."""
import pytest
from lxml import etree

from phase2_project_engine.io import _sec_to_tc, _tc_to_sec
from phase2_project_engine.ops._helpers import (
    playlist_duration, entry_start_sec, shift_entry_on_timeline,
    insert_entry_at_position,
)


def _entry(in_s, out_s, producer="p1"):
    e = etree.Element("entry")
    e.set("producer", producer)
    e.set("in", _sec_to_tc(in_s))
    e.set("out", _sec_to_tc(out_s))
    return e


def _blank(length_s):
    b = etree.Element("blank")
    b.set("length", _sec_to_tc(length_s))
    return b


def test_playlist_duration_empty():
    pl = etree.Element("playlist")
    assert playlist_duration(pl) == 0.0


def test_playlist_duration_none():
    assert playlist_duration(None) == 0.0


def test_playlist_duration_single_entry():
    pl = etree.Element("playlist")
    pl.append(_entry(0.0, 5.0))
    assert playlist_duration(pl) == 5.0


def test_playlist_duration_with_blank():
    pl = etree.Element("playlist")
    pl.append(_entry(0.0, 5.0))
    pl.append(_blank(2.0))
    pl.append(_entry(5.0, 7.0))
    assert playlist_duration(pl) == 9.0


def test_entry_start_sec_first():
    pl = etree.Element("playlist")
    e1 = _entry(0.0, 5.0)
    pl.append(e1)
    assert entry_start_sec(pl, e1) == 0.0


def test_entry_start_sec_after_blank():
    pl = etree.Element("playlist")
    e1 = _entry(0.0, 5.0)
    pl.append(e1)
    pl.append(_blank(2.0))
    e2 = _entry(5.0, 7.0)
    pl.append(e2)
    assert entry_start_sec(pl, e2) == 7.0


def test_entry_start_sec_not_in_playlist():
    pl = etree.Element("playlist")
    e1 = _entry(0.0, 5.0)
    pl.append(e1)
    e2 = _entry(0.0, 1.0)
    # e2 is not a child of pl
    assert entry_start_sec(pl, e2) == 5.0  # walked all of pl


def test_shift_entry_on_timeline_noop_when_shift_zero():
    pl = etree.Element("playlist")
    e = _entry(0.0, 5.0)
    pl.append(e)
    pl.append(_entry(5.0, 10.0))
    shift_entry_on_timeline(pl, e, 0.0)
    assert len(pl.findall("blank")) == 0
    assert len(pl.findall("entry")) == 2


def test_shift_entry_on_timeline_positive_inserts_blank():
    pl = etree.Element("playlist")
    e = _entry(0.0, 5.0)
    pl.append(e)
    pl.append(_entry(5.0, 10.0))
    shift_entry_on_timeline(pl, e, 2.0)
    # A blank of 2s should now precede e
    assert pl[0].tag == "blank"
    assert pl[0].get("length") == _sec_to_tc(2.0)


def test_shift_entry_on_timeline_negative_shrinks_blank():
    pl = etree.Element("playlist")
    pl.append(_blank(5.0))
    e = _entry(0.0, 3.0)
    pl.append(e)
    pl.append(_entry(3.0, 6.0))
    # Shift e left by 1s — should shrink the preceding blank
    shift_entry_on_timeline(pl, e, -1.0)
    assert pl[0].get("length") == _sec_to_tc(4.0)


def test_insert_entry_at_position_into_empty():
    pl = etree.Element("playlist")
    e = _entry(0.0, 5.0)
    insert_entry_at_position(pl, e, 0.0)
    assert pl[0] is e


def test_insert_entry_at_position_at_end():
    pl = etree.Element("playlist")
    e1 = _entry(0.0, 3.0)
    pl.append(e1)
    e2 = _entry(0.0, 2.0)
    insert_entry_at_position(pl, e2, 3.0)
    assert len(pl.findall("entry")) == 2


def test_insert_entry_at_position_in_middle_splits_entry():
    pl = etree.Element("playlist")
    e1 = _entry(0.0, 10.0)
    pl.append(e1)
    e2 = _entry(0.0, 4.0)
    insert_entry_at_position(pl, e2, 4.0)
    # e1 is split at source position 4.0: left=0..4, right=4..10,
    # with e2 inserted in between. The 'in'/'out' attributes are
    # SOURCE positions, not timeline positions.
    entries = pl.findall("entry")
    assert len(entries) == 3
    assert entries[0].get("in") == _sec_to_tc(0.0)
    assert entries[0].get("out") == _sec_to_tc(4.0)
    assert entries[1] is e2
    assert entries[2].get("in") == _sec_to_tc(4.0)
    assert entries[2].get("out") == _sec_to_tc(10.0)
