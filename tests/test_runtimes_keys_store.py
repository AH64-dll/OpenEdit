"""Unit tests for serve/runtimes/keys_store.py (BYOK secure key store)."""
import os
import sys
from pathlib import Path
from open_edit.serve.runtimes.keys_store import (
    save_stored_key,
    get_stored_key,
    load_all_stored_keys,
    mask_key,
    get_masked_keys_summary,
)


def test_mask_key():
    assert mask_key("") == ""
    assert mask_key("short") == "****"
    assert mask_key("sk-ant-api03-abcdefghijkl1234") == "sk-ant-...1234"


def test_save_and_get_stored_key(tmp_path, monkeypatch):
    test_keys_file = tmp_path / ".open_edit" / "keys.json"
    monkeypatch.setattr("open_edit.serve.runtimes.keys_store.KEYS_FILE_PATH", test_keys_file)

    save_stored_key("anthropic", "sk-ant-testkey12345")
    assert test_keys_file.is_file()

    if sys.platform != "win32":
        mode = test_keys_file.stat().st_mode & 0o777
        assert mode == 0o600

    val = get_stored_key("anthropic")
    assert val == "sk-ant-testkey12345"

    summary = get_masked_keys_summary()
    assert summary["anthropic"]["has_key"] is True
    assert "sk-ant-" in summary["anthropic"]["masked_key"]
