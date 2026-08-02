"""Contract tests for render products and stage diagnostics."""

from open_edit.render.diagnostics import StageRecorder, product_descriptor
from open_edit.render.orchestrator import RenderResult


def test_product_descriptor_distinguishes_review_artifact_from_source_proxy():
    descriptor = product_descriptor("proxy", width=640, height=360)
    assert descriptor == {
        "kind": "review_artifact",
        "mode": "proxy",
        "label": "Review artifact",
        "width": 640,
        "height": 360,
        "interactive": False,
        "source_proxy": False,
        "timeline_preview_chunk": False,
    }


def test_stage_recorder_preserves_status_and_numeric_elapsed():
    recorder = StageRecorder()
    recorder.record("remotion_materialize", 1.25, cache_hits=2, cache_misses=1)
    recorder.skip("ffmpeg_encode", reason="deliverable_cache_hit")
    assert recorder.stages["remotion_materialize"]["elapsed_sec"] == 1.25
    assert recorder.stages["remotion_materialize"]["status"] == "completed"
    assert recorder.stages["ffmpeg_encode"] == {
        "elapsed_sec": 0.0,
        "status": "skipped",
        "reason": "deliverable_cache_hit",
    }


def test_legacy_stage_aliases_remain_available():
    result = RenderResult(
        ok=True,
        diagnostics={
            "stages": {
                "melt_video": {"elapsed_sec": 2.0},
                "ffmpeg_encode": {"elapsed_sec": 3.0},
            },
            "legacy_stage_aliases": {
                "melt": "melt_video",
                "ffmpeg": "ffmpeg_encode",
            },
        },
    )
    assert result.diagnostics["legacy_stage_aliases"]["melt"] == "melt_video"
