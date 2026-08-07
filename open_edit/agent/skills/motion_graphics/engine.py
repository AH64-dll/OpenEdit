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
from uuid import uuid4

from pydantic import BaseModel, Field

from open_edit.agent.sandbox import run_render
from open_edit.agent.sandbox.staging import _assets_dir_for_workdir
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
        under a unique ``workdir/_render_output_<run-id>.mp4`` path and ingested into
            ``workdir/assets``.

    Returns:
        An ``AddClipOp`` on the ``video_graphics`` track, with the new
        asset hash and the segment's time range.

    Raises:
        ValueError: if ``template`` is not a known template function.
    """
    template_fn = getattr(templates, template, None)
    if template_fn is None or not callable(template_fn):
        # Beat-type aliases -> template function names (the template package
        # exposes submodules named after beat types, so a bare getattr on
        # e.g. "hook" returns the MODULE, not the render function).
        alias = {
            "hook": "hook_fade_text",
            "turn": "turn_slide_text",
            "scope": "scope_zoom_text",
            "mechanism": "mechanism_diagram",
            "cost": "cost_warning",
            "tease": "tease_glimpse",
            "button": "button_cta",
        }
        template_fn = getattr(templates, alias.get(template, ""), None)
    if template_fn is None or not callable(template_fn):
        raise ValueError(
            f"Unknown template: {template!r}. Available: {', '.join(templates.__all__)}"
        )
    motion_params = MotionTemplateParams(**params)
    duration_s = segment.t_end - segment.t_start
    code = template_fn(motion_params, duration_s)

    # Concurrent template renders must not overwrite one another.
    output_path = workdir / f"_render_output_{uuid4().hex}.mp4"
    render_result = run_render(
        code=code,
        workdir=workdir,
        output_path=output_path,
        timeout_sec=300,
        mem_mb=2048,
    )
    if not render_result.ok:
        raise RuntimeError(
            f"render sandbox failed for template {template!r} "
            f"(segment {segment.beat_type!r}): {render_result.detail}"
        )

    try:
        asset_store = AssetStore(_assets_dir_for_workdir(workdir))
        assets = asset_store.ingest_paths([str(output_path)])
        asset_hash = assets[0].asset_hash
    finally:
        # AssetStore has copied the render into CAS; the render scratch file
        # must not accumulate across repeated or concurrent generations.
        try:
            output_path.unlink(missing_ok=True)
        except OSError:
            pass

    return AddClipOp(
        author="ai",
        asset_hash=asset_hash,
        track_id="video_graphics",
        position_sec=segment.t_start,
        in_point_sec=0.0,
        out_point_sec=duration_s,
    )
