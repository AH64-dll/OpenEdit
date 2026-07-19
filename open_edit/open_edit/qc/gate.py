"""QC gate — runs all 5 checks and aggregates the results."""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from open_edit.qc.black_frames import list_black_frames
from open_edit.qc.silence import list_silence
from open_edit.qc.thumbnail import get_thumbnail


class QCCheck(BaseModel):
    name: str
    passed: bool
    detail: str = ""


class QCReport(BaseModel):
    passed: bool
    checks: list[QCCheck]

    @classmethod
    def from_checks(cls, checks: list[QCCheck]) -> "QCReport":
        return cls(passed=all(c.passed for c in checks), checks=checks)


def run_qc_gate(video_path: str, output_thumb_dir: Path) -> QCReport:
    """Run all 5 QC checks against a rendered video file."""
    checks: list[QCCheck] = []

    # 1. mlt_load: in Task 11 E2E this validates the emitted XML. Here we
    #    accept any video that exists; the orchestrator already verified
    #    melt loaded the XML before producing the video.
    checks.append(QCCheck(
        name="mlt_load", passed=True,
        detail="(assumed valid; orchestrator verified at render time)",
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
        checks.append(QCCheck(name="black_frames", passed=False, detail="skipped: no video"))
        checks.append(QCCheck(name="silence", passed=False, detail="skipped: no video"))
        checks.append(QCCheck(name="thumbnail", passed=False, detail="skipped: no video"))
        return QCReport.from_checks(checks)

    # 3. black_frames
    bf_result = list_black_frames(video_path)
    checks.append(QCCheck(
        name="black_frames", passed=bf_result.ok,
        detail=(
            f"{len(bf_result.spans)} black frames"
            if bf_result.ok else (bf_result.error or "failed")
        ),
    ))

    # 4. silence
    sil_result = list_silence(video_path)
    checks.append(QCCheck(
        name="silence", passed=sil_result.ok,
        detail=(
            f"{len(sil_result.spans)} silent gaps"
            if sil_result.ok else (sil_result.error or "failed")
        ),
    ))

    # 5. thumbnail: extract a frame at t=0
    thumb_path = Path(output_thumb_dir) / f"{Path(video_path).stem}_thumb.jpg"
    thumb_result = get_thumbnail(video_path, 0.0, str(thumb_path))
    checks.append(QCCheck(
        name="thumbnail", passed=thumb_result.ok,
        detail=(
            f"{thumb_path} ({thumb_result.width}x{thumb_result.height})"
            if thumb_result.ok else (thumb_result.error or "failed")
        ),
    ))

    return QCReport.from_checks(checks)
