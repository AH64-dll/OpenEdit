"""Phase 4 Task 7: creativity_level per-project default."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from open_edit.storage.config import get_project_meta, set_project_meta


def test_creativity_level_default(tmp_path, monkeypatch):
    """Fresh project gets creativity_level='balanced' on first read."""
    monkeypatch.setenv("HOME", str(tmp_path))
    meta = get_project_meta("p1")
    assert meta["creativity_level"] == "balanced"


def test_creativity_level_set(tmp_path, monkeypatch):
    """set_project_meta persists; get_project_meta returns the new value."""
    monkeypatch.setenv("HOME", str(tmp_path))
    set_project_meta("p1", "creativity_level", "full")
    meta = get_project_meta("p1")
    assert meta["creativity_level"] == "full"


def test_creativity_level_persists_across_reads(tmp_path, monkeypatch):
    """Reading the meta twice returns the same value (file is cached+re-read)."""
    monkeypatch.setenv("HOME", str(tmp_path))
    set_project_meta("p2", "creativity_level", "conservative")
    m1 = get_project_meta("p2")
    m2 = get_project_meta("p2")
    assert m1["creativity_level"] == m2["creativity_level"] == "conservative"


def test_creativity_level_independent_per_project(tmp_path, monkeypatch):
    """Two projects have independent meta files."""
    monkeypatch.setenv("HOME", str(tmp_path))
    set_project_meta("p_a", "creativity_level", "full")
    set_project_meta("p_b", "creativity_level", "balanced")
    assert get_project_meta("p_a")["creativity_level"] == "full"
    assert get_project_meta("p_b")["creativity_level"] == "balanced"
