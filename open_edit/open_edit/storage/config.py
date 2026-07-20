"""Manages ~/.open-edit/ directory and config files."""
import json
import os
from pathlib import Path


def get_config_dir() -> Path:
    p = Path.home() / ".open-edit"
    p.mkdir(parents=True, exist_ok=True)
    os.chmod(p, 0o700)
    return p


def get_profile_path() -> Path:
    p = get_config_dir() / "style_profile.json"
    if not p.exists():
        p.write_text(json.dumps(_default_profile()))
        os.chmod(p, 0o600)
    return p


def _default_profile() -> dict:
    return {
        "meta": {"version": 0, "updated_at": "", "sample_size": 0, "window": "90d_or_200events"},
        "transitions": {"preferred": [], "avoid": [], "default_duration_s": 1.0, "confidence": 0.0, "examples": []},
        "fades": {"default_in_s": 0.5, "default_out_s": 1.0, "tendency": "", "confidence": 0.0, "examples": []},
        "pacing": {"agent_avg_clip_s": 0.0, "user_avg_clip_s": 0.0, "ratio": 1.0, "tendency": "", "confidence": 0.0, "examples": []},
        "color": {"tendency": "", "confidence": 0.0, "examples": []},
        "audio": {"music_preference": "", "voice_leveling": "", "confidence": 0.0},
        "text_captions": {"style": "", "timing": "", "confidence": 0.0},
        "visual_treatment": {"recurring_effects": [], "confidence": 0.0, "note": ""},
        "structure": {"intro_pattern": "", "outro_pattern": "", "common_shape": ""},
        "export": {"aspect_ratio": "16:9", "resolution": "1080p", "confidence": 0.0},
        "corrections": {"most_overridden_param": "", "direction": "", "note": ""},
        "pinned": {},
    }
