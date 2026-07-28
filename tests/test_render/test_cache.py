"""Tests for the render cache (canonical-JSON hash key)."""
import json
import time
from pathlib import Path

import pytest

from open_edit.render.cache import (
    RenderCache,
    canonical_json_hash,
)


def test_canonical_json_hash_is_deterministic() -> None:
    obj1 = {"b": 2, "a": 1}
    obj2 = {"a": 1, "b": 2}
    assert canonical_json_hash(obj1) == canonical_json_hash(obj2)


def test_canonical_json_hash_differs_for_different_objs() -> None:
    assert canonical_json_hash({"a": 1}) != canonical_json_hash({"a": 2})


def test_canonical_json_hash_handles_nested() -> None:
    obj = {"a": [1, 2, 3], "b": {"c": "hi"}}
    h = canonical_json_hash(obj)
    assert len(h) == 64  # SHA-256 hex


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
    import os
    old_time = time.time() - 7200
    os.utime(cached, (old_time, old_time))
    assert cache.is_fresh(cached, max_age_sec=3600) is False
