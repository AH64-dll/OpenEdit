"""Tests for silence compression planning logic."""
from __future__ import annotations

from open_edit.render.silence_compress import build_keep_ranges


def test_build_keep_ranges_trims_excess_silence():
    silences = [(0.0, 1.0), (5.0, 6.0)]
    keep = build_keep_ranges(10.0, silences, max_silence_s=0.2)
    assert keep == [(0.0, 0.2), (1.0, 5.2), (6.0, 10.0)]


def test_build_keep_ranges_keeps_short_silence():
    silences = [(2.0, 2.15)]
    keep = build_keep_ranges(5.0, silences, max_silence_s=0.2)
    assert keep == [(0.0, 5.0)]


def test_build_keep_ranges_no_silences():
    assert build_keep_ranges(30.0, [], max_silence_s=0.2) == [(0.0, 30.0)]
