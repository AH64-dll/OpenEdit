"""Tag-gated style profile retrieval for system prompt injection.

Per phase4-design-revised.md section 3.2 and spec section 8.8.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from open_edit.storage.config import get_profile_path


TAG_MAP: dict[str, list[str]] = {
    "AddTransition": ["transitions", "corrections"],
    "AddEffect": ["fades", "color", "visual_treatment", "corrections"],
    "SetKeyframe": ["fades", "color", "corrections"],
    "AddClip": ["pacing", "corrections"],
    "MoveClip": ["pacing", "corrections"],
    "TrimClip": ["pacing", "corrections"],
    "RemoveClip": ["pacing", "corrections"],
    "SetAudioGain": ["audio", "corrections"],
    "NormalizeAudio": ["audio", "corrections"],
    "GroupEdits": ["structure", "corrections"],
    "RawMltXml": ["corrections"],
    "FreeFormCode": ["corrections"],
}

CONFIDENCE_THRESHOLD = 0.2
MAX_TOKENS = 250


def get_slice(op_type: str) -> dict[str, Any]:
    profile = json.loads(get_profile_path().read_text())
    categories = TAG_MAP.get(op_type, ["corrections"])
    result: dict[str, Any] = {}
    for cat in categories:
        if cat == "corrections":
            result["corrections"] = profile.get("corrections", {})
            continue
        if cat not in profile:
            continue
        data = profile[cat]
        confidence = data.get("confidence", 0.0) if isinstance(data, dict) else 0.0
        if confidence < CONFIDENCE_THRESHOLD:
            continue
        result[cat] = data
    return _trim_to_token_cap(result)


def _trim_to_token_cap(slice_data: dict[str, Any]) -> dict[str, Any]:
    text = json.dumps(slice_data)
    tokens = len(text) / 4
    if tokens <= MAX_TOKENS:
        return slice_data
    # Trim in order: examples first, then non-essential fields
    for cat in list(slice_data.keys()):
        if cat == "corrections":
            continue
        if "examples" in slice_data[cat]:
            slice_data[cat]["examples"] = []
            text = json.dumps(slice_data)
            tokens = len(text) / 4
            if tokens <= MAX_TOKENS:
                return slice_data
    return slice_data
