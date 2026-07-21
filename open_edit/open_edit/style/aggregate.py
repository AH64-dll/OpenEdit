"""Rule-based rollup of taste events into a style profile.

Per phase4-design-revised.md section 3.2 and spec section 8.6.
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone

from pydantic import BaseModel

from open_edit.style.taste_events import TasteEventStore
from open_edit.storage.config import get_config_dir, get_profile_path


class StyleProfile(BaseModel):
    """Style profile as a bounded, tag-gated summary of past taste events.

    Nested fields are stored as dicts (rather than nested BaseModels) so
    callers can use ``profile.transitions["confidence"]`` and the profile
    can be round-tripped through ``json.loads(json.dumps(profile.model_dump()))``
    for the on-disk file.
    """

    meta: dict
    transitions: dict
    fades: dict
    pacing: dict
    color: dict
    audio: dict
    text_captions: dict
    visual_treatment: dict
    structure: dict
    export: dict
    corrections: dict
    pinned: dict


def rollup(project_id: str, store: TasteEventStore) -> StyleProfile:
    events = store.pull(project_id=project_id, window_days=90, max_events=200)
    profile = json.loads(get_profile_path().read_text())

    weighted_sum_transitions = 0
    examples_transitions = []
    for ev in events:
        if ev.op_type == "AddTransition":
            weight = _weight_for_action(ev.action)
            weighted_sum_transitions += weight
            if ev.action == "applied_modified" and len(examples_transitions) < 4:
                examples_transitions.append({
                    "proposed": ev.proposed_params,
                    "final": ev.final_params,
                    "weight": abs(weight),
                })
    profile["transitions"]["examples"] = examples_transitions
    profile["transitions"]["confidence"] = min(abs(weighted_sum_transitions) / 50, 1.0)
    profile["meta"]["sample_size"] = len(events)
    profile["meta"]["updated_at"] = datetime.now(timezone.utc).isoformat()
    profile["meta"]["version"] = profile["meta"].get("version", 0) + 1

    _write_profile_with_backup(profile)
    store.purge(project_id=project_id)
    return StyleProfile(**profile)


def reset() -> None:
    profile_path = get_profile_path()
    if profile_path.exists():
        profile_path.unlink()
    get_profile_path()  # Re-create with defaults


def set_pinned(key: str, value) -> None:
    profile = json.loads(get_profile_path().read_text())
    profile.setdefault("pinned", {})[key] = value
    _write_profile_with_backup(profile)


def check_rollup_trigger(project_id: str, store: TasteEventStore) -> bool:
    """Per audit M3: triggers are project close, commit_feedback, token budget.

    Token budget: if unrolled events would exceed ~2000 tokens.
    """
    events = store.pull(project_id=project_id, window_days=90, max_events=200)
    estimated_tokens = sum(len(json.dumps(e.model_dump())) for e in events) / 4
    return estimated_tokens >= 2000


def _weight_for_action(action: str) -> int:
    if action == "applied_modified":
        return 5
    if action == "reverted":
        return -3
    return 0  # applied_unmodified


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
    os.chmod(profile_path, 0o600)
