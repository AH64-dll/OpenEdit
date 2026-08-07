"""Tests for the render cache (keyed on the ir edit-graph hash)."""
import json
import os
import time
from pathlib import Path

import pytest

from open_edit.ir.hash import compute_edit_graph_hash
from open_edit.ir.types import AddClipOp
from open_edit.render.cache import (
    DEFAULT_TTL_SEC,
    DEFAULT_RENDER_CACHE_MAX_BYTES,
    RenderCache,
    cache_max_bytes,
    cache_ttl_sec,
    canonical_json_hash,
    parse_cache_max_bytes,
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


def test_render_cache_get_rejects_tampered_content(tmp_path: Path) -> None:
    cache = RenderCache(tmp_path / "cache")
    source = tmp_path / "source.mp4"
    source.write_bytes(b"original")

    cached = cache.put("tampered", source)
    cached.write_bytes(b"tampered")

    assert cache.get("tampered") is None


def test_render_cache_hit_refreshes_lru_access_metadata(
    tmp_path: Path,
) -> None:
    cache = RenderCache(tmp_path / "cache")
    source = tmp_path / "source.mp4"
    source.write_bytes(b"content")
    cached = cache.put("access", source)
    metadata_path = tmp_path / "cache" / ".meta" / "access.mp4.json"
    before = json.loads(metadata_path.read_text(encoding="utf-8"))

    time.sleep(0.01)
    assert cache.get("access") == cached

    after = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert after["schema"] == 2
    assert after["source_hash"] == before["source_hash"]
    assert after["last_accessed_at"] > before["last_accessed_at"]
    assert cached.stat().st_mtime >= before["last_accessed_at"]


def test_render_cache_eviction_uses_least_recently_used_artifacts(
    tmp_path: Path,
) -> None:
    cache = RenderCache(tmp_path / "cache", max_bytes=8)
    first = tmp_path / "first.mp4"
    second = tmp_path / "second.mp4"
    third = tmp_path / "third.mp4"
    first.write_bytes(b"1111")
    second.write_bytes(b"2222")
    third.write_bytes(b"3333")

    first_cached = cache.put("first", first)
    time.sleep(0.01)
    second_cached = cache.put("second", second)
    time.sleep(0.01)
    assert cache.get("first") == first_cached
    time.sleep(0.01)
    third_cached = cache.put("third", third)

    assert first_cached.exists()
    assert not second_cached.exists()
    assert third_cached.exists()


def test_render_cache_byte_cap_excludes_metadata_sidecars(
    tmp_path: Path,
) -> None:
    cache = RenderCache(tmp_path / "cache", max_bytes=8)
    first = tmp_path / "first.mp4"
    second = tmp_path / "second.mp4"
    first.write_bytes(b"1234")
    second.write_bytes(b"5678")

    first_cached = cache.put("first", first)
    second_cached = cache.put("second", second)

    assert first_cached.exists()
    assert second_cached.exists()
    assert sum(
        path.stat().st_size
        for path in (first_cached, second_cached)
    ) == 8


def test_render_cache_retains_fresh_entry_larger_than_cap(
    tmp_path: Path,
) -> None:
    """The just-written entry must never be evicted by its own put().

    The previous behavior copied the artifact and then immediately deleted it
    (put -> evict -> LRU delete) whenever the entry exceeded the cap, which
    made the whole-file cache never hit for renders larger than the cap.
    """
    cache = RenderCache(tmp_path / "cache", max_bytes=3)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"1234")

    cached = cache.put("oversized", source)

    assert cached.exists()
    assert (tmp_path / "cache" / ".meta" / "oversized.mp4.json").exists()
    # A subsequent put makes the oversized entry the LRU victim: the cap is
    # still honored globally.
    second = tmp_path / "second.mp4"
    second.write_bytes(b"ab")
    cache.put("second", second)
    assert not cached.exists()
    assert cache.get("second") is not None


def test_render_cache_max_bytes_parses_units_and_invalid_values() -> None:
    assert parse_cache_max_bytes("2KiB", default=1) == 2 * 1024
    assert parse_cache_max_bytes("3mIb", default=1) == 3 * 1024**2
    assert parse_cache_max_bytes("4GIB", default=1) == 4 * 1024**3
    assert parse_cache_max_bytes("not-a-size", default=17) == 17


def test_render_cache_max_bytes_uses_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPEN_EDIT_RENDER_CACHE_MAX_BYTES", "2MiB")
    monkeypatch.delenv("OPEN_EDIT_REMOTION_CACHE_MAX_BYTES", raising=False)

    assert cache_max_bytes(tmp_path / "cache") == 2 * 1024**2
    assert RenderCache(tmp_path / "cache").max_bytes == 2 * 1024**2


def test_render_cache_invalid_max_bytes_uses_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPEN_EDIT_RENDER_CACHE_MAX_BYTES", "invalid")
    monkeypatch.delenv("OPEN_EDIT_REMOTION_CACHE_MAX_BYTES", raising=False)

    assert cache_max_bytes(tmp_path / "cache") == DEFAULT_RENDER_CACHE_MAX_BYTES


def test_render_cache_wipe_removes_artifacts_and_metadata(
    tmp_path: Path,
) -> None:
    cache = RenderCache(tmp_path / "cache")
    source = tmp_path / "source.mp4"
    source.write_bytes(b"content")
    cached = cache.put("wipe", source)
    metadata = tmp_path / "cache" / ".meta" / "wipe.mp4.json"

    cache.wipe()

    assert not cached.exists()
    assert not metadata.exists()


def test_render_cache_replaces_same_key_when_source_content_changes(
    tmp_path: Path,
) -> None:
    cache = RenderCache(tmp_path / "cache")
    src = tmp_path / "src.mp4"
    src.write_bytes(b"first")
    cached = cache.put("same-key", src)
    assert cached.read_bytes() == b"first"

    src.write_bytes(b"second")
    replaced = cache.put("same-key", src)
    assert replaced == cached
    assert cached.read_bytes() == b"second"
    assert (tmp_path / "cache" / ".meta" / "same-key.mp4.json").is_file()


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


def test_render_cache_key_composes() -> None:
    from open_edit.render.cache import render_cache_key

    key = render_cache_key("hash1", "1080p30|q=standard|enc=gpu")
    assert key == "hash1_1080p30_q=standard_enc=gpu"
    assert key != render_cache_key("hash1", "720p30|q=fast|enc=gpu")


def test_render_cache_key_includes_reference_content() -> None:
    from open_edit.render.cache import render_cache_key

    first = render_cache_key("hash1", "fast_proxy|q=fast", "image-a")
    second = render_cache_key("hash1", "fast_proxy|q=fast", "image-b")
    assert first != second


def test_render_cache_key_is_windows_safe() -> None:
    from open_edit.render.cache import render_cache_key

    key = render_cache_key("hash1", "1080p30|q=standard|enc=gpu")
    assert "|" not in key


def test_render_cache_key_stays_under_filesystem_filename_limit() -> None:
    from open_edit.render.cache import render_cache_key

    key = render_cache_key("graph-hash", "profile", "content-" + "x" * 1000)
    assert len(key) <= 180
    assert "profile" in key
    assert key == render_cache_key("graph-hash", "profile", "content-" + "x" * 1000)
