"""Phase 4 Task 4: STT button visibility is gated by secure context (audit M7).

The Web Speech API is only available in secure contexts (HTTPS, localhost,
file:// in some browsers, etc.). Per audit M7, the STT button must be hidden
when the page is not in a secure context.

The actual decision is made in the browser by static/app.js
(`shouldShowSttButton`). This test verifies the parallel Python helper in
`phase4_chat_ui.secure_context` so the decision logic can be unit-tested
without a browser.
"""
import pytest
from types import SimpleNamespace
from unittest.mock import patch


def _fake_window(*, is_secure: bool, has_speech_recognition: bool = False) -> SimpleNamespace:
    """Build a minimal stand-in for the browser `window` object."""
    return SimpleNamespace(
        isSecureContext=is_secure,
        SpeechRecognition=type("SR", (), {}) if has_speech_recognition else None,
        webkitSpeechRecognition=None,
    )


def test_stt_button_hidden_when_not_secure():
    """Per audit M7: STT requires a secure context; button is hidden otherwise."""
    from phase4_chat_ui import secure_context

    fake_window = _fake_window(is_secure=False, has_speech_recognition=True)
    with patch.object(secure_context, "window", fake_window, create=True):
        assert secure_context.shouldShowSttButton() is False


def test_stt_button_visible_when_secure_and_speech_recognition_available():
    from phase4_chat_ui import secure_context

    fake_window = _fake_window(is_secure=True, has_speech_recognition=True)
    with patch.object(secure_context, "window", fake_window, create=True):
        assert secure_context.shouldShowSttButton() is True


def test_stt_button_hidden_when_secure_but_no_speech_recognition():
    """Per audit M7: even in a secure context, the button is hidden if the
    browser does not expose a SpeechRecognition implementation."""
    from phase4_chat_ui import secure_context

    fake_window = _fake_window(is_secure=True, has_speech_recognition=False)
    with patch.object(secure_context, "window", fake_window, create=True):
        assert secure_context.shouldShowSttButton() is False


def test_stt_button_webkit_prefixed_recognition_counts():
    """webkitSpeechRecognition is the Safari-prefixed implementation; per
    design §3.5 it must satisfy the same check as the unprefixed name."""
    from phase4_chat_ui import secure_context

    fake_window = SimpleNamespace(
        isSecureContext=True,
        SpeechRecognition=None,
        webkitSpeechRecognition=type("WSR", (), {}),
    )
    with patch.object(secure_context, "window", fake_window, create=True):
        assert secure_context.shouldShowSttButton() is True
