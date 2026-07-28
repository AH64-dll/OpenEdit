import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from open_edit.serve.runtimes.keys_store import save_stored_key, load_all_stored_keys


def test_keys_atomic_write_and_permissions():
    with tempfile.TemporaryDirectory() as td:
        keys_file = Path(td) / "keys.json"
        with patch("open_edit.serve.runtimes.keys_store.KEYS_FILE_PATH", keys_file):
            save_stored_key("test_provider", "sk-1234567890abcdef")

            assert keys_file.exists()
            perms = keys_file.stat().st_mode & 0o777
            assert perms <= 0o600, f"Key file permissions too permissive: {oct(perms)}"

            data = json.loads(keys_file.read_text())
            assert data.get("test_provider") == "sk-1234567890abcdef"


def test_load_all_stored_keys():
    with tempfile.TemporaryDirectory() as td:
        keys_file = Path(td) / "keys.json"
        with patch("open_edit.serve.runtimes.keys_store.KEYS_FILE_PATH", keys_file):
            save_stored_key("p1", "key1")
            save_stored_key("p2", "key2")

            loaded = load_all_stored_keys()
            assert loaded == {"p1": "key1", "p2": "key2"}
