"""Focused tests for content-aware derived-cache eviction."""
from __future__ import annotations

import json
from pathlib import Path

from open_edit.ir.types import Asset
from open_edit.render.cache import RenderCache
from open_edit.storage.assets import AssetStore
from open_edit.storage.cache_policy import (
    DEFAULT_CACHE_MAX_AGE_SEC,
    DEFAULT_CACHE_MIN_FREE_BYTES,
    DEFAULT_RENDER_CACHE_MAX_BYTES,
    DEFAULT_REMOTION_CACHE_MAX_BYTES,
    DEFAULT_SOURCE_PROXY_MAX_BYTES,
    CacheSettings,
    enforce_project_cache,
)


def _asset(
    project: Path,
    asset_hash: str,
    *,
    proxy_hash: str | None = None,
    proxy_status: str = "none",
) -> Path:
    assets_dir = project / ".open_edit" / "assets"
    asset_dir = assets_dir / asset_hash[:2]
    asset_dir.mkdir(parents=True, exist_ok=True)
    source_path = asset_dir / asset_hash
    source_path.write_bytes(b"canonical source bytes")
    metadata = Asset(
        asset_hash=asset_hash,
        original_path="source.mp4",
        stored_path=str(source_path),
        type="video",
        duration_sec=1.0,
        width=1920,
        height=1080,
        proxy_hash=proxy_hash,
        proxy_profile="source_proxy_360_v1" if proxy_hash else None,
        proxy_status=proxy_status,
    )
    (asset_dir / f"{asset_hash}.meta.json").write_text(
        metadata.model_dump_json(),
        encoding="utf-8",
    )
    return source_path


def _settings(
    *,
    render: int = 10**9,
    remotion: int = 10**9,
    source_proxy: int = 10**9,
    max_age: int = 0,
    min_free: int = 0,
) -> CacheSettings:
    return CacheSettings(
        render_cache_max_bytes=render,
        remotion_cache_max_bytes=remotion,
        source_proxy_max_bytes=source_proxy,
        max_age_sec=max_age,
        min_free_bytes=min_free,
    )


def test_cache_settings_from_env_rejects_invalid_and_non_positive_values(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPEN_EDIT_RENDER_CACHE_MAX_BYTES", "0")
    monkeypatch.setenv("OPEN_EDIT_REMOTION_CACHE_MAX_BYTES", "bad")
    monkeypatch.setenv("OPEN_EDIT_SOURCE_PROXY_MAX_BYTES", "-1")
    monkeypatch.setenv("OPEN_EDIT_CACHE_MAX_AGE_SEC", "0")
    monkeypatch.setenv("OPEN_EDIT_CACHE_MIN_FREE_BYTES", "nope")

    settings = CacheSettings.from_env()

    assert settings == CacheSettings(
        render_cache_max_bytes=DEFAULT_RENDER_CACHE_MAX_BYTES,
        remotion_cache_max_bytes=DEFAULT_REMOTION_CACHE_MAX_BYTES,
        source_proxy_max_bytes=DEFAULT_SOURCE_PROXY_MAX_BYTES,
        max_age_sec=DEFAULT_CACHE_MAX_AGE_SEC,
        min_free_bytes=DEFAULT_CACHE_MIN_FREE_BYTES,
    )


def test_render_cache_hit_updates_last_access_without_changing_source_hash(
    tmp_path: Path,
) -> None:
    cache = RenderCache(tmp_path / "render_cache")
    source = tmp_path / "source.mp4"
    source.write_bytes(b"render")
    cached = cache.put(
        "key",
        source,
        cache_class="render",
        mode="proxy",
    )
    metadata_path = tmp_path / "render_cache" / ".meta" / "key.mp4.json"
    before = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert cache.get("key") == cached

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["source_hash"] == before["source_hash"]
    assert metadata["last_accessed_at"] >= metadata["updated_at"]
    assert metadata["cache_class"] == "render"
    assert metadata["mode"] == "proxy"


def test_eviction_keeps_canonical_sources_and_active_final(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    canonical = _asset(project, "a" * 64)
    active_final = project / ".open_edit" / "renders" / "project-final.mp4"
    active_final.parent.mkdir(parents=True, exist_ok=True)
    active_final.write_bytes(b"active final deliverable")

    render_cache = RenderCache(project / ".open_edit" / "render_cache")
    render_source = tmp_path / "render-source.mp4"
    render_source.write_bytes(b"old render cache entry")
    render_cache.put("old", render_source, cache_class="render", mode="proxy")

    remotion_cache = project / ".open_edit" / "remotion" / "out" / "cache"
    remotion_cache.mkdir(parents=True, exist_ok=True)
    (remotion_cache / "old.mp4").write_bytes(b"old remotion cache entry")

    report = enforce_project_cache(
        project,
        active_paths=[active_final],
        settings=_settings(render=1, remotion=1, source_proxy=1),
    )

    assert active_final.exists()
    assert canonical.exists()
    assert report.deleted_bytes > 0
    assert report.inspected_bytes >= active_final.stat().st_size
    assert str(canonical) in report.protected_paths
    assert str(active_final) in report.protected_paths


def test_eviction_clears_source_proxy_reference_when_proxy_is_deleted(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    source_hash = "b" * 64
    proxy_hash = "c" * 64
    _asset(
        project,
        source_hash,
        proxy_hash=proxy_hash,
        proxy_status="ready",
    )
    store = AssetStore(project / ".open_edit" / "assets")
    proxy_path = (
        project / ".open_edit" / "assets" / proxy_hash[:2] / proxy_hash
    )
    proxy_path.parent.mkdir(parents=True, exist_ok=True)
    proxy_path.write_bytes(b"derived source proxy bytes")

    report = enforce_project_cache(
        project,
        settings=_settings(source_proxy=1),
    )

    source = store.get(source_hash)
    assert source is not None
    assert source.proxy_hash is None
    assert source.proxy_status == "none"
    assert store.path(proxy_hash) is None
    assert str(proxy_path) in report.deleted_paths


def test_eviction_never_deletes_unreferenced_canonical_cas_bytes(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    canonical = _asset(project, "d" * 64)

    enforce_project_cache(
        project,
        settings=_settings(source_proxy=1),
    )

    assert canonical.exists()


def test_eviction_never_deletes_cas_bytes_with_a_canonical_sidecar(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    source_hash = "e" * 64
    referenced_canonical_hash = "f" * 64
    _asset(project, referenced_canonical_hash)
    _asset(
        project,
        source_hash,
        proxy_hash=referenced_canonical_hash,
        proxy_status="ready",
    )

    enforce_project_cache(
        project,
        settings=_settings(source_proxy=1),
    )

    store = AssetStore(project / ".open_edit" / "assets")
    assert store.path(referenced_canonical_hash) is not None
    linked = store.get(source_hash)
    assert linked is not None
    assert linked.proxy_hash == referenced_canonical_hash


def test_eviction_removes_orphaned_temp_files_but_protects_active_temp(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    temp_dir = project / ".open_edit" / "tmp" / "source-proxy"
    temp_dir.mkdir(parents=True)
    orphan = temp_dir / "orphan.mp4"
    active = temp_dir / "active.mp4"
    orphan.write_bytes(b"orphan")
    active.write_bytes(b"active")

    report = enforce_project_cache(
        project,
        active_paths=[active],
        settings=_settings(),
    )

    assert not orphan.exists()
    assert active.exists()
    assert str(active) in report.protected_paths
