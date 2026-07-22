"""v1.8 — Secure Non-Technical BYOK (Bring Your Own Key) Store.

Stores user-entered API keys in ~/.open_edit/keys.json with restricted (0600)
file permissions so non-technical users can paste API keys directly into the UI
without needing shell environment variables.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

KEYS_FILE_PATH = Path.home() / ".open_edit" / "keys.json"


def _ensure_keys_file_dir() -> Path:
    """Ensure ~/.open_edit directory exists."""
    p = KEYS_FILE_PATH.parent
    p.mkdir(parents=True, exist_ok=True)
    return p


def load_all_stored_keys() -> dict[str, str]:
    """Load stored API keys from ~/.open_edit/keys.json."""
    if not KEYS_FILE_PATH.is_file():
        return {}
    try:
        data = json.loads(KEYS_FILE_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items() if v}
    except Exception:
        pass
    return {}


def save_stored_key(provider: str, key_value: str) -> None:
    """Save an API key for a provider to ~/.open_edit/keys.json with 0600 permissions."""
    _ensure_keys_file_dir()
    current = load_all_stored_keys()
    cleaned_key = key_value.strip()
    if cleaned_key:
        current[provider] = cleaned_key
    else:
        current.pop(provider, None)

    # Write atomically with restricted permissions (0600)
    content = json.dumps(current, indent=2)
    fd, tmp = tempfile.mkstemp(dir=KEYS_FILE_PATH.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        if sys.platform != "win32":
            os.chmod(tmp, 0o600)
        os.replace(tmp, KEYS_FILE_PATH)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def get_stored_key(provider: str) -> str | None:
    """Retrieve stored API key for provider, or None."""
    keys = load_all_stored_keys()
    val = keys.get(provider, "").strip()
    return val if val else None


def mask_key(key: str) -> str:
    """Mask key for UI presentation (e.g. 'sk-a76H...yh2g')."""
    k = key.strip()
    if not k:
        return ""
    if len(k) <= 8:
        return "****"
    return f"{k[:7]}...{k[-4:]}"


def get_masked_keys_summary() -> dict[str, dict[str, Any]]:
    """Return dictionary of provider -> {has_key, masked_key, source}."""
    stored = load_all_stored_keys()
    providers = ["antigravity", "opencode", "anthropic", "openai", "pi", "jcode"]

    env_map = {
        "antigravity": ["ANTIGRAVITY_API_KEY", "OPEN_EDIT_ANTIGRAVITY_KEY"],
        "opencode": ["OPENCODE_API_KEY", "OPEN_EDIT_LLM_API_KEY"],
        "anthropic": ["ANTHROPIC_API_KEY"],
        "openai": ["OPENAI_API_KEY"],
        "pi": ["PI_API_KEY"],
        "jcode": ["JCODE_API_KEY"],
    }

    summary: dict[str, dict[str, Any]] = {}
    for p in providers:
        has_key = False
        masked = ""
        source = "none"

        # Check env
        for env_var in env_map.get(p, []):
            env_val = os.environ.get(env_var, "").strip()
            if env_val:
                has_key = True
                masked = mask_key(env_val)
                source = f"env ({env_var})"
                break

        if not has_key and p in stored:
            has_key = True
            masked = mask_key(stored[p])
            source = "settings (~/.open_edit/keys.json)"

        summary[p] = {
            "has_key": has_key,
            "masked_key": masked,
            "source": source,
        }

    return summary
