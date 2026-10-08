"""Phase 4 T2: Style Memory (aggregate, retrieve, style_inject)."""
from open_edit.style.aggregate import capture_hint, set_pinned
from open_edit.style.retrieve import CONFIDENCE_THRESHOLD, MAX_TOKENS, TAG_MAP, get_slice

__all__ = [
    "CONFIDENCE_THRESHOLD",
    "MAX_TOKENS",
    "TAG_MAP",
    "capture_hint",
    "get_slice",
    "set_pinned",
]
