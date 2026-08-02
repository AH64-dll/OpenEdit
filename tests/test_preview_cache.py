"""Tests for bounded, atomically published preview-chunk storage."""
from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

import pytest

from open_edit.render.preview_cache import PreviewCacheError, PreviewChunkCache
from open_edit.render.preview_manifest import (
    PreviewChunk,
    PreviewManifest,
    PreviewPlaneState,
)


def valid_manifest(*, fallback=None) -> PreviewManifest:
    video = (
        PreviewPlaneState(status="yellow", fallback=fallback)
        if fallback is not None
        else PreviewPlaneState(status="red")
    )
    return PreviewManifest(
        project_id="project",
        graph_revision=1,
        edit_graph_hash="graph",
        duration_frames=30,
        duration_sec=1.0,
        fps_num=30,
        fps_den=1,
        chunk_frames=30,
        profile={"fingerprint": "profile"},
        updated_at=time.time(),
        chunks=[
            PreviewChunk(
                chunk_id="000000-000030",
                index=0,
                start_frame=0,
                end_frame=30,
                start_sec=0.0,
                end_sec=1.0,
                status="yellow" if fallback is not None else "red",
                video=video,
                audio=PreviewPlaneState(status="red"),
                playback=PreviewPlaneState(status="red"),
            )
        ],
    )


def write_artifact(
    cache: PreviewChunkCache,
    tmp_path: Path,
    *,
    key: str,
    content: bytes = b"preview",
    plane: str = "video",
    suffix: str = "mp4",
):
    source = tmp_path / f"{key}.source"
    source.write_bytes(content)
    return cache.commit_artifact(
        plane=plane,
        key=key,
        source=source,
        suffix=suffix,
        graph_hash="graph",
    )


def test_manifest_replace_never_exposes_partial_json(tmp_path: Path) -> None:
    cache = PreviewChunkCache(tmp_path, max_bytes=1_000_000, max_age_sec=None)

    cache.write_manifest(valid_manifest())

    manifest_path = tmp_path / "manifest.json"
    assert PreviewManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    ).schema_version == 1
    assert not list(tmp_path.glob("manifest.json.tmp*"))


def test_read_manifest_rejects_corrupt_json_without_publishing_it(
    tmp_path: Path,
) -> None:
    cache = PreviewChunkCache(tmp_path, max_bytes=1_000_000, max_age_sec=None)
    cache.write_manifest(valid_manifest())

    (tmp_path / "manifest.json").write_text("{", encoding="utf-8")

    assert cache.read_manifest() is None


def test_commit_artifact_validates_content_and_indexes_id(tmp_path: Path) -> None:
    cache = PreviewChunkCache(tmp_path / "cache", max_bytes=1_000_000, max_age_sec=None)
    artifact = write_artifact(cache, tmp_path, key="video-key", content=b"video")

    destination = tmp_path / "cache" / "video" / "video-key.mp4"
    assert artifact.artifact_id == "video-key"
    assert artifact.relative_path == "video/video-key.mp4"
    assert artifact.bytes == 5
    assert artifact.sha256 == hashlib.sha256(b"video").hexdigest()
    assert artifact.graph_hash == "graph"
    assert cache.resolve_artifact("video-key") == destination
    restarted = PreviewChunkCache(
        tmp_path / "cache",
        max_bytes=1_000_000,
        max_age_sec=None,
    )
    assert restarted.resolve_artifact("video-key") == destination
    assert cache.resolve_artifact("video/video-key.mp4") is None
    assert not list((tmp_path / "cache").glob("*.tmp*"))


def test_commit_artifact_rejects_zero_bytes_and_escaping_keys(
    tmp_path: Path,
) -> None:
    cache = PreviewChunkCache(tmp_path, max_bytes=1_000_000, max_age_sec=None)
    empty = tmp_path / "empty.mp4"
    empty.touch()

    with pytest.raises(ValueError):
        cache.commit_artifact(
            plane="video",
            key="empty",
            source=empty,
            suffix="mp4",
            graph_hash="graph",
        )

    source = tmp_path / "source.mp4"
    source.write_bytes(b"content")
    with pytest.raises(ValueError):
        cache.commit_artifact(
            plane="video",
            key="../escape",
            source=source,
            suffix="mp4",
            graph_hash="graph",
        )


def test_resolve_artifact_rejects_unknown_or_escaping_id(
    tmp_path: Path,
) -> None:
    cache = PreviewChunkCache(tmp_path, max_bytes=1_000_000, max_age_sec=None)

    assert cache.resolve_artifact("../secret") is None
    assert cache.resolve_artifact("not-in-index") is None


def test_commit_rejects_below_minimum_free_space_without_partial_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = PreviewChunkCache(
        tmp_path,
        max_bytes=1_000_000,
        max_age_sec=None,
        min_free_bytes=1,
    )
    source = tmp_path / "source.mp4"
    source.write_bytes(b"preview")
    monkeypatch.setattr(
        "open_edit.render.preview_cache.shutil.disk_usage",
        lambda _: type("Usage", (), {"free": 0})(),
    )

    with pytest.raises(PreviewCacheError):
        cache.commit_artifact(
            plane="video",
            key="rejected",
            source=source,
            suffix="mp4",
            graph_hash="graph",
        )

    assert not (tmp_path / "video" / "rejected.mp4").exists()
    assert not list((tmp_path / "video").glob("*.tmp*"))


def test_prune_removes_unreferenced_old_files_before_fallbacks(
    tmp_path: Path,
) -> None:
    cache = PreviewChunkCache(tmp_path, max_bytes=10, max_age_sec=None)
    old = write_artifact(cache, tmp_path, key="old", content=b"1234567890")
    keep = write_artifact(cache, tmp_path, key="keep", content=b"1234567890")
    os.utime(
        tmp_path / old.relative_path,
        (time.time() - 100, time.time() - 100),
    )

    result = cache.prune(valid_manifest(fallback=keep))

    assert result["removed_files"] >= 1
    assert not (tmp_path / old.relative_path).exists()
    assert (tmp_path / keep.relative_path).exists()
    assert cache.resolve_artifact("old") is None


def test_prune_clears_fallback_atomically_when_cap_requires_it(
    tmp_path: Path,
) -> None:
    cache = PreviewChunkCache(tmp_path, max_bytes=1_000_000, max_age_sec=None)
    fallback = write_artifact(cache, tmp_path, key="fallback", content=b"123456")
    cache.write_manifest(valid_manifest(fallback=fallback))
    cache.max_bytes = 1

    result = cache.prune()

    assert result["cleared_fallbacks"] >= 1
    assert cache.read_manifest().chunks[0].video.fallback is None
    assert cache.read_manifest().chunks[0].status == "red"
    assert not (tmp_path / fallback.relative_path).exists()
    assert PreviewManifest.model_validate_json(
        (tmp_path / "manifest.json").read_text(encoding="utf-8")
    )


def test_prune_removes_expired_unreferenced_files(
    tmp_path: Path,
) -> None:
    cache = PreviewChunkCache(tmp_path, max_bytes=1_000_000, max_age_sec=1)
    artifact = write_artifact(cache, tmp_path, key="expired", content=b"old")
    old_time = time.time() - 10
    os.utime(tmp_path / artifact.relative_path, (old_time, old_time))

    result = cache.prune(valid_manifest())

    assert result["removed_files"] == 1
    assert not (tmp_path / artifact.relative_path).exists()


def test_preview_cache_reads_environment_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPEN_EDIT_PREVIEW_CACHE_MAX_BYTES", "2KiB")
    monkeypatch.setenv("OPEN_EDIT_PREVIEW_CACHE_MAX_AGE_SEC", "120")

    cache = PreviewChunkCache(tmp_path)

    assert cache.max_bytes == 2 * 1024
    assert cache.max_age_sec == 120


def test_wipe_removes_all_preview_artifacts_but_not_edit_graph(
    tmp_path: Path,
) -> None:
    cache = PreviewChunkCache(
        tmp_path / ".open_edit" / "preview_chunks",
        max_bytes=1_000_000,
        max_age_sec=None,
    )
    write_artifact(cache, tmp_path, key="wipe", content=b"preview")
    cache.write_manifest(valid_manifest())
    job_tmp = cache.root / "tmp" / "job-1"
    job_tmp.mkdir(parents=True)
    (job_tmp / "partial.mp4").write_bytes(b"partial")
    edit_graph = tmp_path / ".open_edit" / "edit_graph.db"
    edit_graph.write_bytes(b"graph")

    result = cache.wipe()

    assert result["removed_files"] >= 3
    assert not cache.root.joinpath("manifest.json").exists()
    assert not any(cache.root.iterdir())
    assert edit_graph.exists()
