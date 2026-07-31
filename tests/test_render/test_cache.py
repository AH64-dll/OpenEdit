"""Tests for the render cache (keyed on the ir edit-graph hash)."""
import os
import time
from pathlib import Path

import pytest

from open_edit.ir.hash import compute_edit_graph_hash
from open_edit.ir.types import AddClipOp
from open_edit.render.cache import (
    DEFAULT_TTL_SEC,
    RenderCache,
    cache_ttl_sec,
    canonical_json_hash,
)


def _ops() -> list[AddClipOp]:
    return [
        AddClipOp(author="user", asset_hash="a" * 64, track_id="v1",
                  position_sec=0.0, in_point_sec=0.0, out_point_sec=2.0),
        AddClipOp(author="user", asset_hash="b" * 64, track_id="v1",
                  position_sec=2.0, in_point_sec=0.0, out_point_sec=2.0),
    ]


def test_canonical_json_hash_matches_ir_hash() -> None:
    ops = _ops()
    payload = [op.model_dump(mode="json") for op in ops]
    assert canonical_json_hash(payload) == compute_edit_graph_hash(ops)
    assert canonical_json_hash(payload) == compute_edit_graph_hash(payload)


def test_ir_hash_is_order_sensitive_and_content_sensitive() -> None:
    ops = _ops()
    h = compute_edit_graph_hash(ops)
    assert compute_edit_graph_hash(list(reversed(ops))) != h
    changed = _ops()
    changed[0].out_point_sec = 3.0
    assert compute_edit_graph_hash(changed) != h


def test_cache_ttl_default_is_24h() -> None:
    assert DEFAULT_TTL_SEC == 86400
    assert cache_ttl_sec() == 86400


def test_cache_ttl_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPEN_EDIT_RENDER_CACHE_TTL_SEC", "120")
    assert cache_ttl_sec() == 120


def test_cache_ttl_env_invalid_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPEN_EDIT_RENDER_CACHE_TTL_SEC", "not-a-number")
    assert cache_ttl_sec() == DEFAULT_TTL_SEC


def test_render_cache_put_and_get(tmp_path: Path) -> None:
    cache = RenderCache(tmp_path / "cache")
    src = tmp_path / "src.mp4"
    src.write_bytes(b"fake mp4 content")
    h = "abc123"
    cached = cache.put(h, src)
    assert cached.exists()
    retrieved = cache.get(h)
    assert retrieved is not None
    assert retrieved == cached


def test_render_cache_get_miss_returns_none(tmp_path: Path) -> None:
    cache = RenderCache(tmp_path / "cache")
    assert cache.get("nope") is None


def test_render_cache_put_and_get_custom_ext(tmp_path: Path) -> None:
    cache = RenderCache(tmp_path / "cache")
    src = tmp_path / "src.mov"
    src.write_bytes(b"prores content")
    cached = cache.put("movkey", src, ext="mov")
    assert cached.suffix == ".mov"
    assert cache.get("movkey", ext="mov") == cached
    assert cache.get("movkey") is None


def test_render_cache_is_fresh_recent_file(tmp_path: Path) -> None:
    cache = RenderCache(tmp_path / "cache")
    src = tmp_path / "src.mp4"
    src.write_bytes(b"content")
    cached = cache.put("h1", src)
    assert cache.is_fresh(cached) is True


def test_render_cache_is_fresh_old_file(tmp_path: Path) -> None:
    cache = RenderCache(tmp_path / "cache")
    src = tmp_path / "src.mp4"
    src.write_bytes(b"content")
    cached = cache.put("h2", src)
    # Set mtime to 2 hours ago
    old_time = time.time() - 7200
    os.utime(cached, (old_time, old_time))
    assert cache.is_fresh(cached, max_age_sec=3600) is False


def test_render_cache_default_ttl_applies(tmp_path: Path) -> None:
    cache = RenderCache(tmp_path / "cache")
    src = tmp_path / "src.mp4"
    src.write_bytes(b"content")
    cached = cache.put("h3", src)
    # 2 hours old, but default TTL is 24h: still fresh.
    old_time = time.time() - 7200
    os.utime(cached, (old_time, old_time))
    assert cache.is_fresh(cached) is True


def test_render_cache_instance_ttl_overrides_default(tmp_path: Path) -> None:
    cache = RenderCache(tmp_path / "cache", max_age_sec=1800)
    src = tmp_path / "src.mp4"
    src.write_bytes(b"content")
    cached = cache.put("h4", src)
    old_time = time.time() - 7200
    os.utime(cached, (old_time, old_time))
    assert cache.is_fresh(cached) is False
