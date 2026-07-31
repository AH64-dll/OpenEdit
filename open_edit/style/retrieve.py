"""Tag-gated style profile retrieval for system prompt injection.

Per phase4-design-revised.md section 3.2 and spec section 8.8.
"""
from __future__ import annotations

import json
from copy import deepcopy
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


def _load_profile() -> dict[str, Any]:
    try:
        data = json.loads(get_profile_path().read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        pass
    return {}


def get_slice(op_type: str) -> dict[str, Any]:
    profile = _load_profile()
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
    # Always surface recent confirmed hints when present (trimmed later).
    hints = profile.get("hints")
    if isinstance(hints, list) and hints:
        result["hints"] = hints[-5:]
    pinned = profile.get("pinned")
    if isinstance(pinned, dict) and pinned:
        result["pinned"] = pinned
    return _trim_to_token_cap(result)


def _trim_to_token_cap(slice_data: dict[str, Any]) -> dict[str, Any]:
    def _bounded(value: Any) -> Any:
        if isinstance(value, str):
            return value[:300]
        if isinstance(value, dict):
            return {k: _bounded(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_bounded(v) for v in value[:10]]
        return value

    result = deepcopy(slice_data)
    for category, data in result.items():
        if isinstance(data, dict) and "examples" in data:
            data["examples"] = []
    result = _bounded(result)

    def over_budget() -> bool:
        return len(json.dumps(result)) / 4 > MAX_TOKENS

    if not over_budget():
        return result
    # Hints and pinned values are useful, but less important than the
    # operation-specific category. Drop them before dropping that category.
    for optional in ("hints", "pinned", "corrections"):
        result.pop(optional, None)
        if not over_budget():
            return result
    # A malformed profile may contain arbitrarily large nested structures;
    # fail closed rather than injecting an unbounded prompt block.
    return {}
