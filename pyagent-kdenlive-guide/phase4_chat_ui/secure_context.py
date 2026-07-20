"""Browser secure-context detection, mirrored in Python for testability.

The actual client-side check lives in static/app.js (`shouldShowSttButton`).
This Python module mirrors the same decision so the logic can be unit-tested
without a browser. The mirror is intentionally minimal: the JS function is
the source of truth.

Per phase4-design-revised.md §3.5 / audit M7: the Web Speech API is only
exposed in a secure context, and the UI must hide the STT button when the
context is not secure.
"""
from __future__ import annotations

import sys
from types import ModuleType
from typing import Any, Optional


def _self_module() -> ModuleType:
    """Return this module as a ModuleType (helps type-checkers)."""
    mod = sys.modules.get(__name__)
    if mod is None:  # pragma: no cover - defensive
        import phase4_chat_ui.secure_context as mod  # type: ignore[import-not-found]
    return mod  # type: ignore[return-value]


def shouldShowSttButton(window: Optional[Any] = None) -> bool:
    """Decide whether to show the STT (speech-to-text) button.

    Mirrors `shouldShowSttButton()` in `static/app.js`. Returns True only
    when BOTH conditions hold:

    1. The page is in a secure context (`window.isSecureContext === true`).
    2. A `SpeechRecognition` implementation is available — either the
       standard name or the `webkit`-prefixed name.

    Per audit M7: STT requires a secure context; the button is hidden
    otherwise.

    In production, callers pass the browser's `window`. In tests, callers
    either pass a fake window or leave `window=None` and patch the
    module-level `window` attribute (see `tests/test_stt_secure_context.py`).
    """
    target = window if window is not None else getattr(_self_module(), "window", None)
    if target is None:
        return False
    is_secure = bool(getattr(target, "isSecureContext", False))
    has_recognition = (
        getattr(target, "SpeechRecognition", None) is not None
        or getattr(target, "webkitSpeechRecognition", None) is not None
    )
    return is_secure and has_recognition
