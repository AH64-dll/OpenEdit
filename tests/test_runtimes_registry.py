"""Unit tests for serve/runtimes/registry.py (Runtime registry & GUI PATH expansion)."""
import os
from pathlib import Path
from open_edit.serve.runtimes.registry import (
    CANDIDATE_DIRS,
    get_expanded_path_env,
    find_binary_in_expanded_path,
    discover_runtimes,
)


def test_get_expanded_path_env_includes_candidates():
    expanded = get_expanded_path_env()
    assert isinstance(expanded, str)
    assert len(expanded) > 0


def test_find_binary_in_expanded_path(tmp_path, monkeypatch):
    # Create a fake binary in a candidate directory
    fake_bin_dir = tmp_path / "bin"
    fake_bin_dir.mkdir()
    fake_bin = fake_bin_dir / "test_dummy_cli"
    fake_bin.write_text("#!/bin/sh\necho hi\n")
    fake_bin.chmod(0o755)

    monkeypatch.setattr("open_edit.serve.runtimes.registry.CANDIDATE_DIRS", [fake_bin_dir])
    found = find_binary_in_expanded_path("test_dummy_cli")
    assert found is not None
    assert Path(found).resolve() == fake_bin.resolve()


def test_discover_runtimes():
    runtimes = discover_runtimes()
    assert isinstance(runtimes, list)
    assert len(runtimes) > 0
    ids = [r.id for r in runtimes]
    assert "antigravity" in ids
    assert "opencode" in ids
    assert "anthropic" in ids
    assert "openai" in ids
