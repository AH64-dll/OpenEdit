"""v1.8 — Runtime Registry & GUI PATH Expansion.

All provider metadata is defined in ``providers.py`` — the single
canonical registry.  This module provides runtime discovery helpers
(binary lookup on PATH + GUI fallback dirs) and derives ``RuntimeSpec``
from the canonical ``ProviderSpec``.
"""
from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..providers import PROVIDERS


# Standard candidate directories where CLI tools install on macOS/Linux
# even when desktop GUI launchers omit them from $PATH.
# Tests may monkeypatch this list; ``candidate_dirs()`` reads it on POSIX.
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


def _windows_candidate_dirs() -> list[Path]:
    """Common Windows install locations for node/ffmpeg/cli tools."""
    dirs: list[Path] = [
        Path.home() / "AppData" / "Roaming" / "npm",
        Path.home() / ".cargo" / "bin",
        Path.home() / ".bun" / "bin",
        Path.home() / ".local" / "bin",
        Path.cwd() / ".venv" / "Scripts",
    ]
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if local:
        local_p = Path(local)
        dirs.extend([
            local_p / "Programs",
            local_p / "Programs" / "ffmpeg" / "bin",
            local_p / "Microsoft" / "WinGet" / "Links",
        ])
    program_files = os.environ.get("ProgramFiles", "").strip()
    if program_files:
        dirs.append(Path(program_files) / "nodejs")
    return dirs


def candidate_dirs() -> list[Path]:
    """Return platform-appropriate extra PATH candidate directories."""
    if sys.platform == "win32":
        return _windows_candidate_dirs()
    return list(CANDIDATE_DIRS)


def get_expanded_path_env() -> str:
    """Return an expanded PATH string including common CLI install dirs."""
    current = os.environ.get("PATH", "")
    existing = set(current.split(os.pathsep)) if current else set()
    extra: list[str] = []
    for d in candidate_dirs():
        sd = str(d)
        if sd not in existing and d.is_dir():
            extra.append(sd)
    if extra:
        return os.pathsep.join(extra) + os.pathsep + current if current else os.pathsep.join(extra)
    return current


def find_binary_in_expanded_path(binary_name: str) -> str | None:
    """Search for a binary in PATH + common fallback directories."""
    found = shutil.which(binary_name)
    if found:
        return found
    expanded_path = get_expanded_path_env()
    found = shutil.which(binary_name, path=expanded_path)
    if found:
        return found
    # Windows: also try explicit .exe/.cmd next to candidate dirs when which misses.
    if sys.platform == "win32":
        for d in candidate_dirs():
            if not d.is_dir():
                continue
            for name in (binary_name, f"{binary_name}.exe", f"{binary_name}.cmd", f"{binary_name}.bat"):
                candidate = d / name
                if candidate.is_file():
                    return str(candidate)
    return None


@dataclass
class RuntimeSpec:
    """Specification and status of an LLM runtime.

    Fields are derived from the canonical ``ProviderSpec`` in
    ``providers.py`` at discovery time.
    """

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


def discover_runtimes() -> list[RuntimeSpec]:
    """Scan system for installed binaries & configured API keys.

    Derives runtime specs from the canonical :data:`PROVIDERS` dict so
    every provider appears automatically.  Hidden providers are included
    (the runtime discovery endpoint is internal, not user-facing).
    """
    from .keys_store import get_stored_key

    results: list[RuntimeSpec] = []
    for pspec in PROVIDERS.values():
        binary_names: list[str] = list(pspec.binary_names)
        env_keys: list[str] = list(pspec.env_keys)
        models: list[str] = list(pspec.models)

        binary_path: str | None = None
        for bname in binary_names:
            found = find_binary_in_expanded_path(bname)
            if found:
                binary_path = found
                break

        installed = binary_path is not None or len(binary_names) == 0

        has_key = False
        for k in env_keys:
            if os.environ.get(k, "").strip():
                has_key = True
                break
        if not has_key:
            stored_key = get_stored_key(pspec.name)
            if stored_key:
                has_key = True

        results.append(
            RuntimeSpec(
                id=pspec.name,
                name=pspec.label,
                binary_names=binary_names,
                installed=installed,
                binary_path=binary_path,
                env_keys=env_keys,
                has_keys=has_key,
                available_models=models,
            )
        )

    return results
