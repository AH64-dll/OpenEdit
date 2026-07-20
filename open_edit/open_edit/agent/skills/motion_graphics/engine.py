"""Motion graphics engine: runs templates to produce video assets.

Per phase4-design-revised.md section 4.3 (W7). Templated per beat type:
one template function per narrative beat; each takes ``MotionTemplateParams``
and a duration, returns Python source for the render sandbox (W2) to run.

The render sandbox writes a video file; the engine ingests it as a new
asset and emits an ``AddClipOp`` on the conventional ``video_graphics``
track.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from open_edit.agent.sandbox_bridge import run_render
from open_edit.agent.skills.motion_graphics import templates
from open_edit.agent.skills.narrative_analyzer import NarrativeSegment
from open_edit.ir.types import AddClipOp
from open_edit.storage.assets import AssetStore


class MotionTemplateParams(BaseModel):
    """Parameters consumed by every motion-graphics template.

    ``asset_references`` is the v1.1 hook for letting a template reference
    existing project assets (e.g., a product photo for the ``scope`` beat);
    v1 ignores it.
    """

    text: str
    background_color: str = "#000000"
    text_color: str = "#FFFFFF"
    animation_speed: float = 1.0
    asset_references: list[str] = Field(default_factory=list)


def generate_visual(
    segment: NarrativeSegment,
    template: str,
    params: dict,
    project_id: str,
    workdir: Path,
) -> AddClipOp:
    """Run a motion-graphics template, ingest the output, emit AddClipOp.

    Args:
        segment: the narrative beat the visual covers.
        template: name of the template function (looked up on
            ``open_edit.agent.skills.motion_graphics.templates``).
        params: keyword args for ``MotionTemplateParams``.
        project_id: used for tracing/render-sandbox bookkeeping.
        workdir: project working directory; the rendered file is written
            under ``workdir/_render_output.mp4`` and ingested into
            ``workdir/assets``.

    Returns:
        An ``AddClipOp`` on the ``video_graphics`` track, with the new
        asset hash and the segment's time range.

    Raises:
        ValueError: if ``template`` is not a known template function.
    """
    template_fn = getattr(templates, template, None)
    if template_fn is None:
        raise ValueError(f"Unknown template: {template!r}")
    motion_params = MotionTemplateParams(**params)
    duration_s = segment.t_end - segment.t_start
    code = template_fn(motion_params, duration_s)

    output_path = workdir / "_render_output.mp4"
    run_render(
        code=code,
        workdir=workdir,
        output_path=output_path,
        timeout_sec=300,
        mem_mb=2048,
    )

    asset_store = AssetStore(workdir / "assets")
    assets = asset_store.ingest_paths([str(output_path)])
    asset_hash = assets[0].asset_hash

    return AddClipOp(
        author="ai",
        asset_hash=asset_hash,
        track_id="video_graphics",
        position_sec=segment.t_start,
        in_point_sec=0.0,
        out_point_sec=duration_s,
    )
