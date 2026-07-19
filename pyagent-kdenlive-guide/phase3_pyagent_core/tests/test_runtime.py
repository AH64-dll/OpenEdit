"""Tests for the phase3 runtime dispatcher.

These tests call `run_op` directly (not the CLI) to verify the
pure dispatch layer that lives in `phase3_pyagent_core/runtime.py`.
"""
import os
import shutil

import pytest

from phase3_pyagent_core.runtime import run_op


CATALOG_PATH = "phase1_knowledge_base/catalog.json"
FIXTURE_PROJECT = "phase3_pyagent_core/tests/fixtures/demo.kdenlive"


@pytest.fixture
def demo_project(tmp_path):
    if not os.path.exists(FIXTURE_PROJECT):
        pytest.skip(f"fixture missing: {FIXTURE_PROJECT}")
    if not os.path.exists(CATALOG_PATH):
        pytest.skip(f"catalog missing: {CATALOG_PATH}")
    test_proj = tmp_path / "test.kdenlive"
    shutil.copy(FIXTURE_PROJECT, test_proj)
    return str(test_proj)


def test_get_project_info_succeeds(demo_project):
    code, resp = run_op(
        "get_project_info", {}, demo_project, CATALOG_PATH,
    )
    assert code == 0
    assert resp["ok"] is True
    assert resp["result"].fps > 0


def test_unknown_op_returns_fatal(demo_project):
    code, resp = run_op("nonexistent_op", {}, demo_project, CATALOG_PATH)
    assert code == 2
    assert resp["fatal"] is True


def test_validation_error_returns_code_1(demo_project):
    code, resp = run_op(
        "insert_clip",
        {"track_index": 0, "position_sec": -1.0, "source_id": "fake", "source_out_sec": 1.0},
        demo_project, CATALOG_PATH,
    )
    assert code == 1
    assert "fix:" in resp["error"]
