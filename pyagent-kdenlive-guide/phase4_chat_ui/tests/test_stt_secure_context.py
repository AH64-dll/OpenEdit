"""Phase 4 T5/T4-Important: parse static/app.js for client-side logic.

The browser-side decisions live in static/app.js. Rather than mirror them
in Python (which creates a duplicate source of truth), these tests parse
the JS file directly and verify the relevant logic is present.

Per T4 Important #1: drop the Python mirror of `shouldShowSttButton` and
let the test parse the JS file.
Per T4 Important #2: the version-switcher dropdown must change video.src
on change.
"""
from __future__ import annotations

import re
from pathlib import Path

APP_JS = Path(__file__).resolve().parent.parent / "static" / "app.js"


def _read_app_js() -> str:
    return APP_JS.read_text()


def test_should_show_stt_button_hides_when_not_secure():
    """Per audit M7: STT button hidden when window.isSecureContext is false."""
    src = _read_app_js()
    assert "shouldShowSttButton" in src, "JS should define shouldShowSttButton"
    assert "isSecureContext" in src, "JS should check window.isSecureContext"
    assert "SpeechRecognition" in src, "JS should check SpeechRecognition"
    assert "webkitSpeechRecognition" in src, (
        "JS should also check the webkit-prefixed name (Safari)"
    )


def test_should_show_stt_button_called_in_init():
    """The initSttButton() function must call shouldShowSttButton and hide
    the button when it returns false."""
    src = _read_app_js()
    init_match = re.search(
        r"function\s+initSttButton\s*\([^)]*\)\s*\{(.*?)\n\}",
        src,
        re.DOTALL,
    )
    assert init_match, "initSttButton must be defined"
    body = init_match.group(1)
    assert "shouldShowSttButton" in body, (
        "initSttButton must consult shouldShowSttButton"
    )
    assert 'display = "none"' in body, (
        "initSttButton must hide the button when shouldShowSttButton is false"
    )


def test_version_switcher_has_onchange_handler():
    """Per T4 Important #2: selecting a different ready version must update
    video.src. The handler must be wired up in applyVersionList so that
    changing the dropdown swaps the rendered video."""
    src = _read_app_js()
    match = re.search(
        r"function\s+applyVersionList\s*\([^)]*\)\s*\{(.*?)\n\}\n",
        src,
        re.DOTALL,
    )
    assert match, "applyVersionList must be defined in app.js"
    body = match.group(1)
    assert "version-switcher" in body, (
        "applyVersionList must reference the #version-switcher element"
    )
    assert "onchange" in body, (
        "applyVersionList must wire an onchange handler so the dropdown "
        "is interactive (per T4 Important #2)"
    )
    assert "video.src" in body, (
        "applyVersionList must update video.src when the user picks a version"
    )
