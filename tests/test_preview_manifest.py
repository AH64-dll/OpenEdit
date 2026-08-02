"""Tests for the preview manifest and status contract."""
import pytest
from pydantic import ValidationError

from open_edit.render.preview_manifest import (
    PreviewArtifact,
    PreviewChunk,
    PreviewManifest,
    PreviewPlaneState,
    PreviewRange,
    effective_status,
)


def artifact(key: str, graph_hash: str) -> PreviewArtifact:
    return PreviewArtifact(
        artifact_id=key,
        relative_path=f"playback/{key}.mp4",
        mime="video/mp4",
        bytes=1,
        sha256=key,
        graph_hash=graph_hash,
        key=key,
    )


def red_chunk() -> PreviewChunk:
    return PreviewChunk(
        chunk_id="000000-000030",
        index=0,
        start_frame=0,
        end_frame=30,
        start_sec=0.0,
        end_sec=1.0,
        status="red",
        video=PreviewPlaneState(status="red"),
        audio=PreviewPlaneState(status="red"),
        playback=PreviewPlaneState(status="red"),
    )


def test_preview_range_rejects_non_positive_or_reversed_range():
    with pytest.raises(ValidationError):
        PreviewRange(start_sec=1.0, end_sec=1.0)

    with pytest.raises(ValidationError):
        PreviewRange(start_sec=2.0, end_sec=1.0)


def test_manifest_rejects_non_frame_aligned_chunk():
    with pytest.raises(ValidationError):
        PreviewChunk(
            chunk_id="bad",
            index=0,
            start_frame=30,
            end_frame=29,
            start_sec=1.0,
            end_sec=0.966,
            status="red",
            video=PreviewPlaneState(status="red"),
            audio=PreviewPlaneState(status="red"),
            playback=PreviewPlaneState(status="red"),
        )


def test_artifact_rejects_absolute_or_escaping_path():
    with pytest.raises(ValidationError):
        PreviewArtifact(
            artifact_id="x",
            relative_path="/tmp/secret.mp4",
            mime="video/mp4",
            bytes=1,
            sha256="x",
            graph_hash="graph",
            key="x",
        )

    with pytest.raises(ValidationError):
        PreviewArtifact(
            artifact_id="x",
            relative_path="../secret.mp4",
            mime="video/mp4",
            bytes=1,
            sha256="x",
            graph_hash="graph",
            key="x",
        )


def test_dirty_current_with_playable_fallback_is_yellow():
    old = artifact("old-key", "old-graph")
    chunk = PreviewChunk(
        chunk_id="000000-000030",
        index=0,
        start_frame=0,
        end_frame=30,
        start_sec=0.0,
        end_sec=1.0,
        status="yellow",
        video=PreviewPlaneState(status="yellow", fallback=old),
        audio=PreviewPlaneState(status="green", current=artifact("a", "new")),
        playback=PreviewPlaneState(status="yellow", fallback=old),
    )
    assert effective_status(chunk) == "yellow"


def test_no_current_or_fallback_is_red():
    assert effective_status(red_chunk()) == "red"


def test_fully_current_chunk_is_green():
    video = artifact("video", "new")
    audio = artifact("audio", "new")
    playback = artifact("playback", "new")
    chunk = PreviewChunk(
        chunk_id="000000-000030",
        index=0,
        start_frame=0,
        end_frame=30,
        start_sec=0.0,
        end_sec=1.0,
        status="green",
        video=PreviewPlaneState(status="green", current=video),
        audio=PreviewPlaneState(status="green", current=audio),
        playback=PreviewPlaneState(status="green", current=playback),
    )
    assert effective_status(chunk) == "green"


def test_manifest_json_dump_keeps_artifact_path_relative():
    current = artifact("playback", "graph")
    chunk = PreviewChunk(
        chunk_id="000000-000030",
        index=0,
        start_frame=0,
        end_frame=30,
        start_sec=0.0,
        end_sec=1.0,
        status="green",
        video=PreviewPlaneState(status="green"),
        audio=PreviewPlaneState(status="green"),
        playback=PreviewPlaneState(status="green", current=current),
    )
    manifest = PreviewManifest(
        project_id="project",
        graph_revision=0,
        edit_graph_hash="graph",
        duration_frames=30,
        duration_sec=1.0,
        fps_num=30,
        fps_den=1,
        chunk_frames=30,
        profile={"fingerprint": "profile"},
        updated_at=0.0,
        chunks=[chunk],
    )

    payload = manifest.model_dump(mode="json")
    assert payload["schema_version"] == 1
    assert payload["chunks"][0]["playback"]["current"]["relative_path"] == (
        "playback/playback.mp4"
    )
