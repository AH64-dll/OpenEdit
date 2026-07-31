"""Remotion safety and source-hashing helpers.

Entry-point validation, composition source bundling for cache keys, and
cache key derivation. Never shell-interpolates user input.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from open_edit.render.profiles import RenderProfile

REMOTION_VERSION = "4.0.278"


class RemotionRenderError(RuntimeError):
    """Raised when a Remotion composition cannot be rendered."""


def resolve_remotion_root(project_path: Path) -> Path:
    """Return ``<project>/.open_edit/remotion``."""
    return (project_path / ".open_edit" / "remotion").resolve()


def validate_entry_point(project_path: Path, entry_point: str) -> Path:
    """Ensure entry_point stays under ``.open_edit/remotion/``."""
    root = resolve_remotion_root(project_path)
    if not entry_point or entry_point.startswith(("/", "\\")) or ".." in Path(entry_point).parts:
        raise RemotionRenderError(
            f"entry_point must be relative under .open_edit/remotion/; got {entry_point!r}"
        )
    candidate = (root / entry_point).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise RemotionRenderError(
            f"entry_point escapes remotion root: {entry_point!r}"
        ) from exc
    if not candidate.is_file():
        raise RemotionRenderError(f"entry_point not found: {entry_point}")
    return candidate


def composition_source_bundle(project_path: Path, composition_id: str) -> str:
    """Hashable source bundle for one composition (not the whole entry file)."""
    root = resolve_remotion_root(project_path)
    parts: list[str] = []
    comp_path = root / "src" / "compositions" / f"{composition_id}.tsx"
    if comp_path.is_file():
        parts.append(comp_path.read_text(encoding="utf-8"))
    root_tsx = root / "src" / "Root.tsx"
    if root_tsx.is_file():
        text = root_tsx.read_text(encoding="utf-8")
        marker = f'id="{composition_id}"'
        idx = text.find(marker)
        if idx >= 0:
            # Include only this composition's registration block.
            start = text.rfind("<Composition", 0, idx)
            end = text.find("/>", idx)
            if start >= 0 and end >= 0:
                parts.append(text[start : end + 2])
            else:
                parts.append(text)
        else:
            parts.append(text)
    return "\n---\n".join(parts)


def composition_cache_key(
    *,
    composition_source: str,
    composition_id: str,
    props: dict[str, Any],
    profile: RenderProfile,
    alpha: bool,
    duration_sec: float,
) -> str:
    payload = {
        "composition_source": composition_source,
        "composition_id": composition_id,
        "props": props,
        "profile": profile.model_dump(),
        "alpha": alpha,
        "duration_sec": duration_sec,
        "remotion_version": REMOTION_VERSION,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()
