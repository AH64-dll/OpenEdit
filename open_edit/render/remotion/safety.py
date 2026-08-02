"""Remotion safety and source-hashing helpers.

Entry-point validation, composition source bundling for cache keys, and
cache key derivation. Never shell-interpolates user input.
"""
from __future__ import annotations

import hashlib
import json
import filecmp
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any
from urllib.parse import unquote, urlparse
import re

from open_edit.render.profiles import RenderProfile

REMOTION_VERSION = "4.0.278"
ALPHA_POLICY_VERSION = "alpha-auto-v1"
PUBLIC_ASSET_STAGE_VERSION = "public-assets-v1"


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


def _iter_prop_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_prop_strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_prop_strings(item)


def _referenced_paths(
    project_path: Path,
    composition_source: str,
    props: dict[str, Any],
) -> list[Path]:
    root = resolve_remotion_root(project_path)
    public = root / "public"
    candidates: list[Path] = []
    static_refs = re.findall(
        r"""staticFile\(\s*["']([^"']+)["']\s*\)""",
        composition_source,
    )
    for ref in static_refs:
        candidate = (public / ref).resolve()
        if candidate == public.resolve() or public.resolve() in candidate.parents:
            candidates.append(candidate)
    for value in _iter_prop_strings(props):
        candidate: Path | None = None
        if value.startswith("file://"):
            parsed = urlparse(value)
            candidate = Path(unquote(parsed.path))
        else:
            possible = Path(value).expanduser()
            if possible.is_absolute():
                candidate = possible
            elif "/" in value or "\\" in value or (public / value).exists():
                candidate = public / value
        if candidate is not None:
            candidates.append(candidate.resolve())
    unique: dict[str, Path] = {}
    for candidate in candidates:
        unique[str(candidate)] = candidate
    return [unique[key] for key in sorted(unique)]


def stage_referenced_assets(
    project_path: Path,
    composition_source: str,
    props: dict[str, Any],
) -> list[Path]:
    """Copy local composition assets into Remotion's safe public directory.

    Remotion's ``staticFile`` only serves files below ``public``. Composition
    props commonly carry ``file://`` paths to project-local images, so resolve
    those paths and stage them by basename before rendering. Missing or
    out-of-project files fail closed instead of producing a broken image.
    """
    project_root = Path(project_path).resolve()
    public_root = (resolve_remotion_root(project_root) / "public").resolve()
    public_root.mkdir(parents=True, exist_ok=True)
    staged: list[Path] = []

    for candidate in _referenced_paths(project_root, composition_source, props):
        source = candidate.resolve()
        if not source.is_file():
            raise RemotionRenderError(
                f"referenced Remotion asset not found: {source}",
            )
        try:
            source.relative_to(project_root)
        except ValueError as exc:
            raise RemotionRenderError(
                f"referenced Remotion asset escapes project root: {source}",
            ) from exc

        try:
            relative_public = source.relative_to(public_root)
            destination = (public_root / relative_public).resolve()
        except ValueError:
            destination = (public_root / source.name).resolve()
        try:
            destination.relative_to(public_root)
        except ValueError as exc:
            raise RemotionRenderError(
                f"Remotion public asset destination escapes public root: {destination}",
            ) from exc
        if destination == source:
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.is_file() and filecmp.cmp(source, destination, shallow=False):
            staged.append(destination)
            continue

        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=destination.parent,
                prefix=f".{destination.name}.",
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
            shutil.copy2(source, temporary)
            os.replace(temporary, destination)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        staged.append(destination)
    return staged


def referenced_file_fingerprints(
    project_path: Path,
    composition_source: str,
    props: dict[str, Any],
) -> list[dict[str, str]]:
    """Hash referenced files, following symlinks to their target bytes."""
    fingerprints: list[dict[str, str]] = []
    for path in _referenced_paths(project_path, composition_source, props):
        resolved = path.resolve()
        if resolved.is_file():
            digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
        else:
            digest = "<missing>"
        fingerprints.append({
            "path": str(path),
            "resolved_path": str(resolved),
            "sha256": digest,
        })
    return fingerprints


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
    source = "\n---\n".join(parts)
    files = referenced_file_fingerprints(project_path, source, {})
    return (
        source
        + "\n---public-asset-staging---\n"
        + PUBLIC_ASSET_STAGE_VERSION
        + "\n---referenced-files---\n"
        + json.dumps(files, sort_keys=True, separators=(",", ":"))
    )


def composition_cache_key(
    *,
    composition_source: str,
    composition_id: str,
    props: dict[str, Any],
    profile: RenderProfile,
    alpha: bool,
    duration_sec: float,
    project_path: Path | None = None,
) -> str:
    referenced_files = (
        referenced_file_fingerprints(project_path, composition_source, props)
        if project_path is not None else []
    )
    payload = {
        "composition_source": composition_source,
        "composition_id": composition_id,
        "props": props,
        "profile": profile.model_dump(),
        "alpha": alpha,
        "duration_sec": duration_sec,
        "remotion_version": REMOTION_VERSION,
        "alpha_policy_version": ALPHA_POLICY_VERSION,
        "referenced_files": referenced_files,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def render_reference_fingerprint(
    project_path: Path,
    compositions: list[Any],
    alpha_mode: str = "auto",
) -> str:
    """Hash all Remotion source, props, and referenced file bytes for a render."""
    records: list[dict[str, Any]] = []
    for composition in compositions:
        source = composition_source_bundle(
            project_path, composition.composition_id,
        )
        records.append({
            "composition_id": composition.composition_id,
            "props": composition.props,
            "source": source,
            "files": referenced_file_fingerprints(
                project_path, source, composition.props,
            ),
            "alpha": composition.alpha,
            "alpha_mode": alpha_mode if composition.alpha else "opaque",
            "duration_sec": composition.duration_sec,
        })
    blob = json.dumps(
        records, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()
