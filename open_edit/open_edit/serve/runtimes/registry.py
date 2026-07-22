"""v1.8 — Extensible Runtime Registry & GUI PATH Expansion.

Inspired by nexu-io/open-design (runtimes/registry.ts).
Provides structured runtime discovery across both system PATH and common
GUI fallback directories (~/.local/bin, ~/.npm-global/bin, /opt/homebrew/bin)
so desktop launches don't report false "not installed" failures.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# Standard candidate directories where CLI tools install on macOS/Linux
# even when desktop GUI launchers omit them from $PATH.
CANDIDATE_DIRS: list[Path] = [
    Path.home() / ".local" / "bin",
    Path.home() / ".npm-global" / "bin",
    Path.home() / ".cargo" / "bin",
    Path.home() / ".bun" / "bin",
    Path("/opt/homebrew/bin"),
    Path("/usr/local/bin"),
    Path("/usr/bin"),
    Path("/bin"),
]


def get_expanded_path_env() -> str:
    """Return an expanded PATH string including common CLI install dirs."""
    current = os.environ.get("PATH", "")
    existing = set(current.split(os.pathsep)) if current else set()
    extra: list[str] = []
    for d in CANDIDATE_DIRS:
        sd = str(d)
        if sd not in existing and d.is_dir():
            extra.append(sd)
    if extra:
        return os.pathsep.join(extra) + os.pathsep + current if current else os.pathsep.join(extra)
    return current


def find_binary_in_expanded_path(binary_name: str) -> str | None:
    """Search for a binary in PATH + common fallback directories."""
    # First try standard PATH lookup
    found = shutil.which(binary_name)
    if found:
        return found
    # Try candidate dirs
    expanded_path = get_expanded_path_env()
    return shutil.which(binary_name, path=expanded_path)


@dataclass
class RuntimeSpec:
    """Specification and status of a CLI LLM runtime."""

    id: str
    name: str
    binary_names: list[str]
    installed: bool = False
    binary_path: str | None = None
    env_keys: list[str] = field(default_factory=list)
    has_keys: bool = False
    available_models: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "installed": self.installed,
            "binary_path": self.binary_path,
            "has_keys": self.has_keys,
            "available_models": self.available_models,
        }


# Registry of supported CLI runtimes
RUNTIME_SPECS: list[dict[str, Any]] = [
    {
        "id": "antigravity",
        "name": "Antigravity (Google)",
        "binary_names": ["agy", "antigravity"],
        "env_keys": ["ANTIGRAVITY_API_KEY", "OPEN_EDIT_ANTIGRAVITY_KEY"],
        "models": [
            "gemini-2.5-flash",
            "gemini-3.5-flash-high",
            "gemini-3.5-flash-medium",
            "gemini-3.6-flash-high",
            "gemini-3.1-pro-high",
            "claude-sonnet-4.6",
            "claude-opus-4.6",
            "gpt-oss-120b",
        ],
    },
    {
        "id": "opencode",
        "name": "OpenCode CLI",
        "binary_names": ["opencode"],
        "env_keys": ["OPENCODE_API_KEY", "OPEN_EDIT_LLM_API_KEY"],
        "models": [
            "opencode-go/minimax-m3",
            "opencode-go/claude-sonnet-4-5",
            "opencode-go/deepseek-v4-pro",
        ],
    },
    {
        "id": "pi",
        "name": "Pi Agent Engine",
        "binary_names": ["pi"],
        "env_keys": ["PI_API_KEY"],
        "models": [
            "minimax-m3",
            "minimax-m2.7",
            "deepseek-v4-flash",
            "deepseek-v4-pro",
        ],
    },
    {
        "id": "jcode",
        "name": "JCode CLI",
        "binary_names": ["jcode"],
        "env_keys": ["JCODE_API_KEY"],
        "models": ["jcode-default"],
    },
    {
        "id": "anthropic",
        "name": "Anthropic Claude API",
        "binary_names": [],
        "env_keys": ["ANTHROPIC_API_KEY"],
        "models": [
            "claude-sonnet-4-5",
            "claude-3-5-sonnet-latest",
            "claude-3-5-haiku-latest",
            "claude-3-opus-latest",
        ],
    },
    {
        "id": "openai",
        "name": "OpenAI API",
        "binary_names": [],
        "env_keys": ["OPENAI_API_KEY"],
        "models": ["gpt-4o", "gpt-4o-mini", "o3-mini"],
    },
]


def discover_runtimes() -> list[RuntimeSpec]:
    """Scan system for installed CLI binaries & configured API keys."""
    from .keys_store import get_stored_key

    results: list[RuntimeSpec] = []
    for spec in RUNTIME_SPECS:
        rt_id = spec["id"]
        binary_names: list[str] = spec.get("binary_names", [])
        env_keys: list[str] = spec.get("env_keys", [])
        models: list[str] = spec.get("models", [])

        binary_path: str | None = None
        for bname in binary_names:
            found = find_binary_in_expanded_path(bname)
            if found:
                binary_path = found
                break

        installed = binary_path is not None or len(binary_names) == 0

        # Check if an API key is present in env or local key store
        has_key = False
        for k in env_keys:
            if os.environ.get(k, "").strip():
                has_key = True
                break

        if not has_key:
            # Check local BYOK store
            stored_key = get_stored_key(rt_id)
            if stored_key:
                has_key = True

        results.append(
            RuntimeSpec(
                id=rt_id,
                name=spec["name"],
                binary_names=binary_names,
                installed=installed,
                binary_path=binary_path,
                env_keys=env_keys,
                has_keys=has_key,
                available_models=models,
            )
        )

    return results
