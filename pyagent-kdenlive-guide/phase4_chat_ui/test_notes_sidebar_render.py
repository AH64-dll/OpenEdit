"""Notes sidebar UI tests — verifies the static HTML + JS wiring for the
Phase 4 T6 unified-notes surface (per design §3.6).

No browser is used. The checks read the static files and assert the
element IDs and WS message types the brief requires.
"""
from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_APP_JS = _REPO_ROOT / "phase4_chat_ui" / "static" / "app.js"
_INDEX_HTML = _REPO_ROOT / "phase4_chat_ui" / "static" / "index.html"


def _read(path: Path) -> str:
    assert path.exists(), f"static file not found at {path}"
    return path.read_text(encoding="utf-8")


def test_index_html_has_notes_section():
    html = _read(_INDEX_HTML)
    for token in [
        'id="notes-count"',
        'id="notes-list"',
        'id="notes-view-all"',
        'id="notes-modal"',
        'class="notes-section"',
    ]:
        assert token in html, f"expected {token!r} in index.html"


def test_app_js_renders_notes_from_note_list_message():
    js = _read(_APP_JS)
    # JS must define the render function and dispatch on `note_list`.
    for token in [
        "renderNotesSection",
        "renderNotesSection(msg.notes",
        "anchorLabel",
        "formatTime",
        "openNotesModal",
    ]:
        assert token in js, f"expected {token!r} in app.js"


def test_app_js_handles_note_list_ws_message():
    js = _read(_APP_JS)
    assert 'case "note_list":' in js
    assert "renderNotesSection" in js
