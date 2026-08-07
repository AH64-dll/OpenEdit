"""Host melt→ffmpeg PreviewVideoRenderer for preview-chunk video planes."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from open_edit.ir.types import Timeline
from open_edit.render.emitter import EmitterConfig, emit_timeline
from open_edit.render.encoder import EncoderSpec
from open_edit.render.frame_engine import PreviewVideoRequest
from open_edit.render.materialize import materialize_remotion_compositions
from open_edit.render.hyperframes import materialize_hyperframes_overlays
from open_edit.render.pipe_builder import OverlayClip
from open_edit.render.preview_pipe import build_preview_pipe_commands
from open_edit.render.profiles import RenderProfile, resolve_encoder_args
from open_edit.render.timeline_plan import build_render_plan
from open_edit.storage.assets import AssetStore

log = logging.getLogger(__name__)


class HostPreviewVideoRenderer:
    """Render one preview-chunk video range via melt rawvideo → ffmpeg.

    Remotion compositions overlapping the request are materialized through the
    existing host materialize path and burned as overlay clips. This keeps the
    chunk worker on the ``PreviewVideoRenderer`` seam without inventing a
    second Remotion bake program.
    """

    def __init__(
        self,
        project_path: Path,
        *,
        melt_bin: str | None = None,
        encoder: EncoderSpec | None = None,
    ) -> None:
        self.project_path = Path(project_path).resolve()
        self.melt_bin = melt_bin or shutil.which("melt") or "melt"
        self.encoder = encoder

    def render(self, request: PreviewVideoRequest) -> Path:
        # Local import avoids a module cycle with preview_chunks at import time.
        from open_edit.render.preview_chunks import run_preview_pipe

        profile = request["profile"]
        if not isinstance(profile, RenderProfile):
            raise TypeError("preview video request requires a RenderProfile")
        output_path = Path(request["output_path"])
        output_path.parent.mkdir(parents=True, exist_ok=True)

        timeline = request["timeline"]
        if not isinstance(timeline, Timeline):
            raise TypeError("preview video request requires a Timeline")

        composition_uids = tuple(request.get("composition_uids") or ())
        if timeline.remotion_compositions:
            force_uids = composition_uids or tuple(
                composition.composition_uid
                for composition in timeline.remotion_compositions
            )
            timeline = materialize_remotion_compositions(
                timeline,
                self.project_path,
                mode="proxy",
                force_uids=force_uids,
                profile_fingerprint=(
                    f"preview-chunk|{profile.width}x{profile.height}|"
                    f"{profile.frame_rate_num}/{profile.frame_rate_den}"
                ),
            )

        hyperframes_result = materialize_hyperframes_overlays(
            timeline,
            self.project_path,
            mode="proxy",
            width=profile.width,
            height=profile.height,
            fps=profile.frame_rate_num / max(profile.frame_rate_den, 1),
        )

        store = AssetStore(self.project_path / ".open_edit" / "assets")
        plan = build_render_plan(
            timeline,
            [],
            store,
            "proxy",
            frame_engine="materialize",
            frame_profile=profile,
            emission_profile="preview-chunk",
            enqueue_missing_proxies=False,
        )
        xml_path = output_path.with_suffix(".mlt")
        xml_path.write_text(
            emit_timeline(
                plan.melt_timeline,
                EmitterConfig(profile=profile.model_dump()),
                asset_paths=plan.asset_paths,
                hwaccel=True,
            ),
            encoding="utf-8",
        )
        overlays = [
            overlay
            for overlay in plan.overlay_clips
            if isinstance(overlay, OverlayClip)
        ]
        if hyperframes_result is not None:
            overlays.append(OverlayClip(
                position_sec=0.0,
                duration_sec=timeline.duration_sec,
                media_path=hyperframes_result.output_path,
                label="hyperframes",
                alpha=True,
            ))
            overlays.sort(key=lambda overlay: overlay.position_sec)

        crop_head = int(request["core_start_frame"]) - int(
            request["render_start_frame"]
        )
        crop_tail = int(request["render_end_frame"]) - int(
            request["core_end_frame"]
        )
        core_frames = int(request["core_end_frame"]) - int(
            request["core_start_frame"]
        )
        if core_frames <= 0:
            raise ValueError("preview video core range must be positive")

        encoder = self.encoder or resolve_encoder_args(profile)
        commands = build_preview_pipe_commands(
            melt_bin=self.melt_bin,
            xml_path=xml_path,
            video_output=output_path,
            audio_output=None,
            playback_output=output_path.with_name(
                f"{output_path.stem}-playback.mp4"
            ),
            profile=profile,
            encoder=encoder,
            overlays=overlays,
            crop_head_frames=max(0, crop_head),
            crop_tail_frames=max(0, crop_tail),
            core_frames=core_frames,
            media="video",
        )
        log.debug(
            "host preview video render core=%s-%s crop_head=%s crop_tail=%s "
            "overlays=%s out=%s",
            request["core_start_frame"],
            request["core_end_frame"],
            crop_head,
            crop_tail,
            len(overlays),
            output_path,
        )
        run_preview_pipe(commands)
        return output_path


__all__ = ["HostPreviewVideoRenderer"]
