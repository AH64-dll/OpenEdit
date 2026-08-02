"""Tests for Remotion dirty-zone selection and manifest persistence."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from open_edit.render.remotion.dirty import (
    DirtySelection,
    load_manifest,
    select_dirty_compositions,
    write_manifest_atomic,
)


def clip(
    clip_id: str,
    position_sec: float,
    duration_sec: float,
    asset_hash: str,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "clip_id": clip_id,
        "track_id": "v1",
        "asset_hash": asset_hash,
        "position_sec": position_sec,
        "duration_sec": duration_sec,
        "in_point_sec": 0.0,
        "out_point_sec": duration_sec,
        **extra,
    }


def comp(
    uid: str,
    position_sec: float,
    duration_sec: float,
    cache_key: str,
    asset_hash: str,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "composition_uid": uid,
        "composition_id": "TitleCard",
        "position_sec": position_sec,
        "duration_sec": duration_sec,
        "cache_key": cache_key,
        "asset_hash": asset_hash,
        "ext": "mp4",
        "alpha": False,
        **extra,
    }


def manifest(
    *,
    clips: list[dict[str, Any]] | None = None,
    compositions: list[dict[str, Any]] | None = None,
    mode: str = "proxy",
    profile_fingerprint: str = "proxy-profile",
) -> dict[str, Any]:
    return {
        "schema": 1,
        "mode": mode,
        "profile_fingerprint": profile_fingerprint,
        "graph_hash": "graph-hash",
        "clips": clips or [],
        "compositions": compositions or [],
    }


def test_base_edit_selects_only_overlapping_remotion_uids() -> None:
    previous = manifest(
        clips=[clip("talk", 0.0, 20.0, "asset-a")],
        compositions=[
            comp("inside", 4.0, 3.0, "key-inside", "hash-inside"),
            comp("outside", 12.0, 2.0, "key-outside", "hash-outside"),
        ],
    )
    current = manifest(
        clips=[clip("talk", 0.0, 20.0, "asset-b")],
        compositions=[
            comp("inside", 4.0, 3.0, "key-inside", "hash-inside"),
            comp("outside", 12.0, 2.0, "key-outside", "hash-outside"),
        ],
    )

    selection = select_dirty_compositions(previous, current)

    assert selection == DirtySelection(
        intervals=((0.0, 20.0),),
        composition_uids=frozenset({"inside", "outside"}),
    )


def test_half_open_intervals_do_not_select_boundary_compositions() -> None:
    previous = manifest(
        clips=[clip("talk", 0.0, 4.0, "asset-a")],
        compositions=[
            comp("before", 2.0, 2.0, "before-key", "before-hash"),
            comp("at-end", 4.0, 1.0, "at-end-key", "at-end-hash"),
        ],
    )
    current = manifest(
        clips=[clip("talk", 0.0, 4.0, "asset-b")],
        compositions=[
            comp("before", 2.0, 2.0, "before-key", "before-hash"),
            comp("at-end", 4.0, 1.0, "at-end-key", "at-end-hash"),
        ],
    )

    selection = select_dirty_compositions(previous, current)

    assert selection.intervals == ((0.0, 4.0),)
    assert selection.composition_uids == frozenset({"before"})


def test_changed_added_and_removed_clips_merge_touching_ranges() -> None:
    previous = manifest(
        clips=[
            clip("changed", 0.0, 2.0, "old"),
            clip("removed", 4.0, 2.0, "old"),
        ],
        compositions=[
            comp("removed-comp", 4.5, 0.5, "removed-key", "removed-hash"),
        ],
    )
    current = manifest(
        clips=[
            clip("changed", 0.0, 3.0, "new"),
            clip("added", 2.0, 2.0, "new"),
        ],
        compositions=[],
    )

    selection = select_dirty_compositions(previous, current)

    assert selection.intervals == ((0.0, 6.0),)
    assert selection.composition_uids == frozenset()


def test_content_change_is_dirty_even_without_an_overlapping_base_edit() -> None:
    previous = manifest(compositions=[comp("card", 2.0, 1.0, "old-key", "old-hash")])
    current = manifest(compositions=[comp("card", 2.0, 1.0, "new-key", "old-hash")])

    selection = select_dirty_compositions(previous, current)

    assert selection.composition_uids == frozenset({"card"})


def test_profile_alpha_duration_and_force_changes_select_current_uids() -> None:
    previous = manifest(
        compositions=[
            comp("profile", 1.0, 1.0, "profile-key", "profile-hash"),
            comp("alpha", 2.0, 1.0, "alpha-key", "alpha-hash"),
            comp("duration", 3.0, 1.0, "duration-key", "duration-hash"),
            comp("forced", 4.0, 1.0, "forced-key", "forced-hash"),
        ],
    )
    current = manifest(
        profile_fingerprint="new-profile",
        compositions=[
            comp("profile", 1.0, 1.0, "profile-key", "profile-hash"),
            comp("alpha", 2.0, 1.0, "alpha-key", "alpha-hash", alpha=True, ext="webm"),
            comp("duration", 3.0, 2.0, "duration-key", "duration-hash"),
            comp("forced", 4.0, 1.0, "forced-key", "forced-hash"),
        ],
    )

    selection = select_dirty_compositions(previous, current, force_uids={"forced"})

    assert selection.composition_uids == frozenset(
        {"profile", "alpha", "duration", "forced"},
    )


def test_manifest_is_written_atomically_only_after_success(tmp_path: Path) -> None:
    path = tmp_path / "materialize_manifest.proxy.json"
    expected = manifest(compositions=[])

    write_manifest_atomic(path, expected)

    assert load_manifest(path) == expected
    assert not list(tmp_path.glob("*.tmp"))
    assert load_manifest(tmp_path / "missing.json") is None
