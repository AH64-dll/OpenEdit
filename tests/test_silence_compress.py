"""Tests for silence compression planning logic."""
from __future__ import annotations

import inspect
from pathlib import Path
from unittest import mock

import pytest

from open_edit.render.silence_compress import (
    build_keep_ranges,
    compress_silence,
)


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


def test_compress_silence_has_no_workers_param():
    """Task 7.2: the reserved workers param was deleted."""
    assert "workers" not in inspect.signature(compress_silence).parameters


def test_compress_silence_uses_provided_gaps(tmp_path: Path):
    """When gaps are provided, detection is skipped and they drive the keep ranges."""
    src = tmp_path / "in.mp4"
    src.write_bytes(b"fake")
    out = tmp_path / "out.mp4"
    with mock.patch(
        "open_edit.render.silence_compress.probe_duration",
        side_effect=[10.0, 9.0],
    ) as probe, mock.patch(
        "open_edit.render.silence_compress.detect_silence_spans",
    ) as detect, mock.patch(
        "open_edit.render.silence_compress._concat_ranges",
    ) as concat:
        stats = compress_silence(src, out, gaps=[(1.0, 1.6)])
    detect.assert_not_called()
    assert probe.call_count == 2
    # gap (1.0, 1.6) with max_silence_s=0.2 -> keep [0,1.2) + [1.6,10)
    concat.assert_called_once()
    _, ranges, _out = concat.call_args.args
    assert _out == out
    assert ranges == [(0.0, 1.2), (1.6, 10.0)]
    assert stats["changed"] is True
    assert stats["removed_s"] == pytest.approx(0.4)
    assert stats["silence_count"] == 1


def test_compress_silence_empty_gaps_copies(tmp_path: Path):
    """Empty gaps -> no removals -> straight copy, no concat, no detection."""
    src = tmp_path / "in.mp4"
    src.write_bytes(b"fake")
    out = tmp_path / "out.mp4"
    with mock.patch(
        "open_edit.render.silence_compress.probe_duration",
        return_value=10.0,
    ), mock.patch(
        "open_edit.render.silence_compress.detect_silence_spans",
    ) as detect, mock.patch(
        "open_edit.render.silence_compress.shutil.copy2",
    ) as copy2, mock.patch(
        "open_edit.render.silence_compress._concat_ranges",
    ) as concat:
        stats = compress_silence(src, out, gaps=[])
    detect.assert_not_called()
    concat.assert_not_called()
    copy2.assert_called_once_with(src, out)
    assert stats["changed"] is False
    assert stats["removed_s"] == 0.0
