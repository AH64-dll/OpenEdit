"""Tests for the asset path fixes in Wave 1 Task 1."""
from __future__ import annotations

import tempfile
from pathlib import Path

from open_edit.agent.tools._helpers import get_asset_store


def test_get_asset_store_uses_dot_open_edit_prefix() -> None:
    """The canonical assets dir is <workdir>/.open_edit/assets/."""
    with tempfile.TemporaryDirectory() as td:
        workdir = Path(td)
        (workdir / ".open_edit" / "assets").mkdir(parents=True)
        st = get_asset_store(str(workdir))
        assert st.assets_dir == workdir / ".open_edit" / "assets"

    with tempfile.TemporaryDirectory() as td:
        workdir = Path(td) / "myproject"
        (workdir / ".open_edit" / "assets").mkdir(parents=True)
        st = get_asset_store(str(workdir))
        assert st.assets_dir == workdir / ".open_edit" / "assets"
