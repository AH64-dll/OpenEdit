"""Tests for phase2_project_engine.backend — the thin dispatch layer.

Three tests:
  1. EditorBackend cannot be instantiated (it's abstract).
  2. KdenliveFileBackend can be constructed from a real .kdenlive file
     and returns a sane ProjectInfo.
  3. KdenliveFileBackend can be constructed in-memory (project_path=None)
     and returns a zero-duration empty project.
"""
from __future__ import annotations

import os

import pytest

from phase2_project_engine.backend import (
    EditorBackend,
    KdenliveFileBackend,
    ProjectInfo,
    TimelineSummary,
)
from phase2_project_engine.catalog import Catalog
from phase2_project_engine.errors import BackendError


_FIXTURE_PATH = "phase3_pyagent_core/tests/fixtures/demo.kdenlive"


def test_backend_is_abstract():
    with pytest.raises(TypeError):
        EditorBackend()  # cannot instantiate abstract class


def test_construct_with_project_path():
    if not os.path.exists(_FIXTURE_PATH):
        pytest.skip(f"fixture missing: {_FIXTURE_PATH}")
    backend = KdenliveFileBackend(
        project_path=_FIXTURE_PATH,
        catalog=Catalog(effects=[], transitions=[], generators=[]),
    )
    info = backend.get_project_info()
    assert isinstance(info, ProjectInfo)
    assert info.fps > 0
    assert info.width > 0
    assert info.height > 0


def test_construct_in_memory():
    backend = KdenliveFileBackend(
        project_path=None,
        catalog=Catalog(effects=[], transitions=[], generators=[]),
    )
    info = backend.get_project_info()
    assert info.path is None
    assert info.duration_sec == 0.0
    assert info.fps > 0
