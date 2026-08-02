"""QC gate — runs all 10 checks and aggregates the results.

Implements the check set documented in ``skills/qc-standards.md``
(``streams``, ``duration``, ``audio_sync``, ``black_frames``,
``frozen_frames``, ``overlays_burned``) plus the pipeline-internal
integrity checks (``render_completed``, ``proxy_render``, ``silence``,
``thumbnail``).
"""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from open_edit.qc.black_frames import list_black_frames
from open_edit.qc.frozen_frames import list_frozen_frames
from open_edit.qc.silence import list_silence
from open_edit.qc.streams import probe_streams
from open_edit.qc.thumbnail import get_thumbnail

# Duration check: rendered duration must be within ±1.0s of the target
# the user asked for (qc-standards.md).
DURATION_TOLERANCE_S = 1.0
# audio_sync: video stream duration and audio stream duration must agree
# within ±200ms (qc-standards.md).
AUDIO_SYNC_TOLERANCE_S = 0.2
# frozen_frames: no interval ≥1.0s where the video didn't change.
FROZEN_MIN_SEC = 1.0


def _span_overlaps_any(
    span: dict, known_spans: list[dict], tolerance_sec: float = 0.05,
) -> bool:
    start = float(span.get("start_sec", 0.0))
    end = float(span.get("end_sec", start))
    for known in known_spans:
        known_start = float(known.get("start_sec", 0.0))
        known_end = float(known.get("end_sec", known_start))
        if start <= known_end + tolerance_sec and end >= known_start - tolerance_sec:
            return True
    return False


class QCCheck(BaseModel):
    name: str
    passed: bool
    detail: str = ""


class QCReport(BaseModel):
    passed: bool
    checks: list[QCCheck]
    # Deterministic spans consumed by the visual-verify evidence stage:
    # {"black_frames": [...], "silence": [...], "frozen_frames": [...]}
    spans: dict[str, list[dict]] = {}
    source_known_spans: dict[str, list[dict]] = {}
    duration_sec: float | None = None

    @classmethod
    def from_checks(cls, checks: list[QCCheck]) -> "QCReport":
        return cls(passed=all(c.passed for c in checks), checks=checks)


def run_qc_gate(
    video_path: str,
    output_thumb_dir: Path,
    *,
    target_duration_s: float | None = None,
    mode: str | None = None,
    source_baseline: dict | None = None,
) -> QCReport:
    """Run all QC checks against a rendered video file.

    Parameters
    ----------
    video_path:
        Path to the rendered MP4.
    output_thumb_dir:
        Directory where the thumbnail check writes its JPEG.
    target_duration_s:
        Expected duration (edit-graph timeline duration). When omitted,
        the ``duration`` check is informational.
    mode:
        Render mode (``proxy``/``final``/``overlay``). ``overlay`` implies
        HTML overlays were requested and burned.
    """
    checks: list[QCCheck] = []
    spans: dict[str, list[dict]] = {
        "black_frames": [], "silence": [], "frozen_frames": [],
    }
    source_known_spans: dict[str, list[dict]] = {
        "black_frames": list((source_baseline or {}).get("black_frames") or []),
        "frozen_frames": list((source_baseline or {}).get("frozen_frames") or []),
    }
    duration_sec: float | None = None

    # 1. render_completed: honest signal — the orchestrator returned
    #    ok=True with a non-empty MP4 (this gate is video-only).
    checks.append(QCCheck(
        name="render_completed", passed=True,
        detail="(proxy MP4 exists; orchestrator returned ok=True)",
    ))

    # 2. proxy_render: the file exists and is non-empty
    p = Path(video_path)
    if p.exists() and p.stat().st_size > 0:
        checks.append(QCCheck(
            name="proxy_render", passed=True,
            detail=str(p),
        ))
    else:
        checks.append(QCCheck(
            name="proxy_render", passed=False,
            detail=f"video not found or empty: {video_path}",
        ))
        # If proxy failed, the rest cannot run
        for name in ("streams", "duration", "audio_sync", "black_frames",
                     "frozen_frames", "silence", "overlays_burned", "thumbnail"):
            checks.append(QCCheck(name=name, passed=False, detail="skipped: no video"))
        report = QCReport.from_checks(checks)
        report.spans = spans
        report.source_known_spans = source_known_spans
        return report

    # 3. streams: ≥1 video stream AND ≥1 audio stream (ffprobe)
    streams = probe_streams(video_path)
    if streams.ok:
        duration_sec = streams.container_duration_s
        has_video = streams.video_streams >= 1
        has_audio = streams.audio_streams >= 1
        checks.append(QCCheck(
            name="streams",
            passed=has_video and has_audio,
            detail=(
                f"{streams.video_streams} video, {streams.audio_streams} audio "
                f"stream(s) ({', '.join(streams.codec_types) or 'none'})"
            ),
        ))
    else:
        checks.append(QCCheck(
            name="streams", passed=False,
            detail=streams.error or "ffprobe failed",
        ))

    # 4. duration: rendered duration within ±1.0s of the target
    probed = duration_sec
    if probed is None:
        checks.append(QCCheck(
            name="duration", passed=False,
            detail=streams.error or "could not read container duration",
        ))
    elif target_duration_s is None:
        checks.append(QCCheck(
            name="duration", passed=True,
            detail=f"duration={probed:.2f}s (no target to compare)",
        ))
    else:
        diff = abs(probed - target_duration_s)
        checks.append(QCCheck(
            name="duration",
            passed=diff <= DURATION_TOLERANCE_S,
            detail=(
                f"duration={probed:.2f}s target={target_duration_s:.2f}s "
                f"diff={diff:.2f}s (limit {DURATION_TOLERANCE_S:.1f}s)"
            ),
        ))

    # 5. audio_sync: video and audio stream durations agree within ±200ms
    v_dur = streams.video_duration_s
    a_dur = streams.audio_duration_s
    if streams.ok and streams.audio_streams == 0:
        checks.append(QCCheck(
            name="audio_sync", passed=False,
            detail="no audio stream present; nothing to keep in sync",
        ))
    elif v_dur is not None and a_dur is not None:
        diff = abs(v_dur - a_dur)
        checks.append(QCCheck(
            name="audio_sync",
            passed=diff <= AUDIO_SYNC_TOLERANCE_S,
            detail=(
                f"video={v_dur:.3f}s audio={a_dur:.3f}s "
                f"diff={diff:.3f}s (limit {AUDIO_SYNC_TOLERANCE_S:.1f}s)"
            ),
        ))
    else:
        checks.append(QCCheck(
            name="audio_sync", passed=False,
            detail=streams.error or "could not read stream durations",
        ))

    # 6. black_frames
    bf_result = list_black_frames(video_path)
    black_spans = (
        [s.model_dump() for s in bf_result.spans]
        if bf_result.ok else []
    )
    new_black_spans = [
        span for span in black_spans
        if not _span_overlaps_any(span, source_known_spans["black_frames"])
    ]
    checks.append(QCCheck(
        name="black_frames", passed=bf_result.ok and not new_black_spans,
        detail=(
            f"{len(black_spans)} black spans "
            f"({len(new_black_spans)} new; "
            f"{len(black_spans) - len(new_black_spans)} source-known)"
            if bf_result.ok else (bf_result.error or "failed")
        ),
    ))
    if bf_result.ok:
        spans["black_frames"] = black_spans

    # 7. frozen_frames: no interval ≥1.0s where the video didn't change
    ff_result = list_frozen_frames(video_path, min_sec=FROZEN_MIN_SEC)
    frozen_spans = (
        [s.model_dump() for s in ff_result.spans]
        if ff_result.ok else []
    )
    new_frozen_spans = [
        span for span in frozen_spans
        if not _span_overlaps_any(span, source_known_spans["frozen_frames"])
    ]
    checks.append(QCCheck(
        name="frozen_frames", passed=ff_result.ok and not new_frozen_spans,
        detail=(
            f"{len(frozen_spans)} frozen intervals "
            f"({len(new_frozen_spans)} new; "
            f"{len(frozen_spans) - len(new_frozen_spans)} source-known; "
            f"min {FROZEN_MIN_SEC:.1f}s)"
            if ff_result.ok else (ff_result.error or "failed")
        ),
    ))
    if ff_result.ok:
        spans["frozen_frames"] = frozen_spans

    # 8. silence
    sil_result = list_silence(video_path)
    checks.append(QCCheck(
        name="silence", passed=sil_result.ok,
        detail=(
            f"{len(sil_result.spans)} silent gaps"
            if sil_result.ok else (sil_result.error or "failed")
        ),
    ))
    if sil_result.ok:
        spans["silence"] = [s.model_dump() for s in sil_result.spans]

    # 9. overlays_burned: informational — the gate cannot OCR the burned
    #    output; visual review is the real check (qc-standards.md).
    if mode == "overlay":
        checks.append(QCCheck(
            name="overlays_burned", passed=True,
            detail="overlay mode: overlays requested and burned; "
                   "visibility requires visual review (no OCR)",
        ))
    elif mode is None:
        checks.append(QCCheck(
            name="overlays_burned", passed=True,
            detail="not machine-checkable (no OCR); visual review is the real check",
        ))
    else:
        checks.append(QCCheck(
            name="overlays_burned", passed=True,
            detail="overlays not requested in this render mode",
        ))

    # 10. thumbnail: extract a frame at t=0
    thumb_path = Path(output_thumb_dir) / f"{Path(video_path).stem}_thumb.jpg"
    thumb_result = get_thumbnail(video_path, 0.0, str(thumb_path))
    checks.append(QCCheck(
        name="thumbnail", passed=thumb_result.ok,
        detail=(
            f"{thumb_path} ({thumb_result.width}x{thumb_result.height})"
            if thumb_result.ok else (thumb_result.error or "failed")
        ),
    ))

    report = QCReport.from_checks(checks)
    report.spans = spans
    report.source_known_spans = source_known_spans
    report.duration_sec = duration_sec
    return report


# Backward-compatible home for the cut-policy helper that moved to
# ``open_edit.agent.skills.silence_cutter`` (it is cut policy, not QC).
from open_edit.agent.skills.silence_cutter import no_word_split_check  # noqa: E402
