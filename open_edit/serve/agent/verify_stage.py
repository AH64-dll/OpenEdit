"""Visual verification helpers (v1.5)."""
from __future__ import annotations

import asyncio
import base64
import os
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from open_edit.kernel.render_overlay import _probe_duration

from .. import visual_verify


def _render_failure_source(error_msg: str) -> str:
    """Map a render error string to a ``verdict_source`` value."""
    if "render_failed" in error_msg:
        return "render_failed"
    if "no_video_stream" in error_msg:
        return "no_video_stream"
    if "frame_extraction_failed" in error_msg:
        return "frame_extraction_failed"
    if "timeout" in error_msg:
        return "timeout"
    if "empty_render" in error_msg or "render_invalid" in error_msg:
        return "empty_render"
    return "render_failed"


def _build_verification_result(
    *,
    render_id: str,
    render_path: str,
    outcome: str,
    verdict_source: str,
    render_count: int,
    max_renders: int,
) -> dict[str, Any]:
    """Build a single ``verification_result`` AgentEvent."""
    return {
        "type": "verification_result",
        "render_id": render_id,
        "render_path": render_path,
        "outcome": outcome,
        "verdict_source": verdict_source,
        "render_count": render_count,
        "max_renders": max_renders,
    }


async def _maybe_verify_render(
    result: dict[str, Any],
    project_path: Path,
    render_count: int,
    cfg: dict[str, Any],
    should_cancel: Callable[[], bool] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any] | None]:
    """Run the verification stage for one ``trigger_render`` result.

    Returns ``(events, augmented_result, pending)``:
    - ``events``: AgentEvents to yield in order.
    - ``augmented_result``: the tool result the LLM sees.
    - ``pending``: state to track across the next LLM response so the
      LLM's verdict can be parsed. ``None`` for terminal paths.
    """
    events: list[dict[str, Any]] = []
    render_id = result.get("render_id", "render_unknown")
    output_path = result.get("output_path", "")
    mode = result.get("mode", "proxy")
    max_renders = cfg["max_renders"]

    # Non-blocking trigger_render returns job_id only — defer verification
    # until the agent polls get_render_job / wait=true path produces output.
    if result.get("job_id") and not output_path:
        events.append(_build_verification_result(
            render_id=str(result.get("job_id")),
            render_path="",
            outcome="skipped",
            verdict_source="queued_async",
            render_count=render_count,
            max_renders=max_renders,
        ))
        return events, result, None

    if result.get("no_change"):
        events.append(_build_verification_result(
            render_id=render_id,
            render_path=output_path,
            outcome="skipped",
            verdict_source="no_change",
            render_count=render_count,
            max_renders=max_renders,
        ))
        return events, result, None

    if "error" in result:
        events.append(_build_verification_result(
            render_id=render_id,
            render_path=output_path,
            outcome="failed",
            verdict_source=_render_failure_source(result["error"]),
            render_count=render_count,
            max_renders=max_renders,
        ))
        return events, result, None

    mp4_path = Path(output_path)
    if not output_path or not mp4_path.exists() or mp4_path.stat().st_size == 0:
        invalid = visual_verify.build_failure_tool_result(
            "empty_render", render_id=render_id, path=output_path,
        )
        events.append(_build_verification_result(
            render_id=render_id,
            render_path=output_path,
            outcome="failed",
            verdict_source="empty_render",
            render_count=render_count,
            max_renders=max_renders,
        ))
        return events, invalid, None

    try:
        duration_s = await asyncio.to_thread(_probe_duration, mp4_path)
    except Exception:
        invalid = visual_verify.build_failure_tool_result(
            "no_video_stream", render_id=render_id, detail=str(output_path),
        )
        events.append(_build_verification_result(
            render_id=render_id,
            render_path=output_path,
            outcome="failed",
            verdict_source="no_video_stream",
            render_count=render_count,
            max_renders=max_renders,
        ))
        return events, invalid, None

    frames_ts = visual_verify.sample_frames(duration_s, override_count=cfg["frames"])
    model_id = os.environ.get("OPEN_EDIT_LLM_MODEL", "minimax-m3")
    cap = visual_verify.model_capability(model_id)
    supports_images = bool(cap.get("supports_images", False))

    events.append({
        "type": "verification_started",
        "render_id": render_id,
        "render_path": output_path,
        "frame_count": cfg["frames"],
        "stage": "sampling",
    })

    if not supports_images:
        events.append(_build_verification_result(
            render_id=render_id,
            render_path=output_path,
            outcome="skipped",
            verdict_source="text_only_model",
            render_count=render_count,
            max_renders=max_renders,
        ))
        augmented = visual_verify.build_verification_tool_result(
            {"render_id": render_id, "output_path": output_path, "duration_s": duration_s},
            [], cap, mode,
        )
        return events, augmented, None

    events.append({
        "type": "verification_started",
        "render_id": render_id,
        "render_path": output_path,
        "frame_count": len(frames_ts),
        "stage": "encoding",
    })

    tmpdir = Path(tempfile.mkdtemp(prefix="oe_verify_"))
    try:
        frames: list[dict[str, Any]] = []
        for ts in frames_ts:
            if should_cancel and should_cancel():
                events.append(_build_verification_result(
                    render_id=render_id,
                    render_path=output_path,
                    outcome="skipped",
                    verdict_source="user_cancelled",
                    render_count=render_count,
                    max_renders=max_renders,
                ))
                fail = visual_verify.build_failure_tool_result(
                    "frame_extraction_failed",
                    render_id=render_id,
                    detail="cancelled by user",
                )
                return events, fail, None
            frame_path = tmpdir / f"frame_{int(ts * 1000)}.jpg"
            try:
                await asyncio.to_thread(
                    visual_verify.encode_jpeg,
                    mp4_path,
                    frame_path,
                    cfg["max_edge_px"],
                    cfg["jpeg_quality"],
                    cfg["max_image_bytes"],
                )
            except Exception as exc:
                events.append(_build_verification_result(
                    render_id=render_id,
                    render_path=output_path,
                    outcome="failed",
                    verdict_source="frame_extraction_failed",
                    render_count=render_count,
                    max_renders=max_renders,
                ))
                fail = visual_verify.build_failure_tool_result(
                    "frame_extraction_failed", render_id=render_id, detail=str(exc),
                )
                return events, fail, None
            with frame_path.open("rb") as f:
                data = base64.b64encode(f.read()).decode("ascii")
            frames.append({
                "mimeType": "image/jpeg",
                "data": data,
                "t_seconds": ts,
            })

        events.append({
            "type": "verification_started",
            "render_id": render_id,
            "render_path": output_path,
            "frame_count": len(frames),
            "stage": "ready",
        })

        render_output = {
            "render_id": render_id,
            "output_path": output_path,
            "duration_s": duration_s,
        }
        augmented = visual_verify.build_verification_tool_result(
            render_output, frames, cap, mode,
        )
        pending = {
            "render_id": render_id,
            "output_path": output_path,
            "render_count": render_count,
            "max_renders": max_renders,
            "supports_images": supports_images,
            "verdict": "unknown",
            "notes": "",
        }
        return events, augmented, pending
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
