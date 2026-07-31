"""Phase 4 T2: Style Memory (aggregate, retrieve, style_inject)."""
from open_edit.style.aggregate import capture_hint, set_pinned
from open_edit.style.retrieve import get_slice, TAG_MAP, CONFIDENCE_THRESHOLD, MAX_TOKENS

__all__ = [
    "capture_hint",
    "set_pinned",
    "get_slice",
    "TAG_MAP",
    "CONFIDENCE_THRESHOLD",
    "MAX_TOKENS",
]
