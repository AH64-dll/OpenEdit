"""Phase 4.5 W2: render sandbox Python wrapper."""
import pytest
from pathlib import Path
from open_edit.agent.sandbox_bridge import _resolve_render_binary


def test_resolve_render_binary():
    """The binary is in one of the known locations."""
    binary = _resolve_render_binary()
    assert binary.exists()
    assert binary.is_file()
