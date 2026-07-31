"""Style profile persistence (pinned overrides + confirmed hints).

Per phase4-design-revised.md section 3.2 and spec section 8.6.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime, timezone
from typing import Any

from open_edit.storage.config import get_config_dir, get_profile_path, _default_profile


def _load_profile() -> dict[str, Any]:
    path = get_profile_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        pass
    return _default_profile()


def set_pinned(key: str, value) -> None:
    profile = _load_profile()
    profile.setdefault("pinned", {})[key] = value
    _touch_meta(profile)
    _write_profile_with_backup(profile)


def capture_hint(
    *,
    category: str,
    hint: str,
    key: str | None = None,
    value: Any = None,
    source: str = "user_confirmed",
) -> dict[str, Any]:
    """Persist a confirmed style hint with provenance.

    Also pins ``key=value`` when both are provided.
    """
    category = (category or "other").strip() or "other"
    hint = (hint or "").strip()
    if not hint:
        raise ValueError("hint must be non-empty")

    profile = _load_profile()
    entry = {
        "text": hint,
        "category": category,
        "source": source,
        "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if key:
        entry["key"] = key

    hints = profile.setdefault("hints", [])
    if not isinstance(hints, list):
        hints = []
        profile["hints"] = hints
    hints.append(entry)
    # Cap history so the profile stays prompt-friendly.
    if len(hints) > 50:
        profile["hints"] = hints[-50:]

    # Fold into corrections.note for retrieve() categories that only see corrections.
    corrections = profile.setdefault("corrections", {})
    if not isinstance(corrections, dict):
        corrections = {}
        profile["corrections"] = corrections
    note = str(corrections.get("note") or "").strip()
    line = f"[{category}] {hint}"
    corrections["note"] = f"{note}\n{line}".strip() if note else line

    # Raise confidence slightly on the named category when it exists as a dict.
    cat_data = profile.get(category)
    if isinstance(cat_data, dict):
        conf = float(cat_data.get("confidence") or 0.0)
        cat_data["confidence"] = min(1.0, max(conf, 0.35))
        examples = cat_data.setdefault("examples", [])
        if isinstance(examples, list):
            examples.append(hint)
            cat_data["examples"] = examples[-5:]

    if key is not None and value is not None:
        profile.setdefault("pinned", {})[key] = value

    _touch_meta(profile)
    _write_profile_with_backup(profile)
    return entry


def _touch_meta(profile: dict[str, Any]) -> None:
    meta = profile.setdefault("meta", {})
    if not isinstance(meta, dict):
        meta = {}
        profile["meta"] = meta
    meta["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    meta["sample_size"] = int(meta.get("sample_size") or 0) + 1


def _write_profile_with_backup(profile: dict) -> None:
    profile_path = get_profile_path()
    config_dir = get_config_dir()
    # Rotate last 3 versions
    for i in range(2, 0, -1):
        src = config_dir / f"style_profile_v{i}.json.bak"
        dst = config_dir / f"style_profile_v{i+1}.json.bak"
        if src.exists():
            shutil.copy2(src, dst)
    if profile_path.exists():
        shutil.copy2(profile_path, config_dir / "style_profile_v1.json.bak")
    # Clean up old backups beyond 3
    for f in config_dir.glob("style_profile_v[4-9]*.json.bak"):
        f.unlink()
    profile_path.write_text(json.dumps(profile, indent=2))
    if sys.platform != "win32":
        os.chmod(profile_path, 0o600)
