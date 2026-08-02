"""Contract tests for the M1 renderer seam consumed by preview chunks."""
from __future__ import annotations

from pathlib import Path

from open_edit.ir.types import Timeline
from open_edit.render.frame_engine import (
    PreviewVideoRenderer,
    PreviewVideoRequest,
)
from open_edit.render.profiles import RenderProfile


def test_preview_renderer_receives_core_and_context_frames(tmp_path: Path) -> None:
    seen: dict[str, object] = {}

    class Fake:
        def render(self, request: PreviewVideoRequest) -> Path:
            seen.update(request)
            request["output_path"].write_bytes(b"video")
            return request["output_path"]

    renderer: PreviewVideoRenderer = Fake()
    output = tmp_path / "video.mp4"
    request: PreviewVideoRequest = {
        "project_dir": tmp_path,
        "timeline": Timeline(),
        "render_start_frame": 28,
        "render_end_frame": 62,
        "core_start_frame": 30,
        "core_end_frame": 60,
        "composition_uids": ("comp-a", "comp-b"),
        "profile": RenderProfile(
            name="preview_chunk",
            width=640,
            height=360,
            frame_rate_num=30,
            frame_rate_den=1,
        ),
        "output_path": output,
    }

    got = renderer.render(request)

    assert got == output
    assert seen["composition_uids"] == ("comp-a", "comp-b")
    assert (seen["render_start_frame"], seen["render_end_frame"]) == (28, 62)
    assert (seen["core_start_frame"], seen["core_end_frame"]) == (30, 60)
