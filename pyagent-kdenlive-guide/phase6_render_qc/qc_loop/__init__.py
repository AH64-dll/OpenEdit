"""Conversational QC loop.

Per the Phase 6 plan, after an applied edit (or on request), the QC flow
should be: render a ranged proxy around the change → run the deterministic
checks first → only pull a thumbnail/crop/audio sample for anything the
deterministic checks flagged or the user specifically asked about.

This module orchestrates that flow. The LLM can call each tool
individually for fine control, or call ``qc_check()`` once and get a
structured report.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from phase6_render_qc import audio, black_frames
from phase6_render_qc.render import render
from phase6_render_qc.thumbnails import get_thumbnail


@dataclass
class QcFlag:
    kind: str  # "black" | "silence" | "low_audio"
    start_sec: float
    end_sec: float
    detail: str


@dataclass
class QcReport:
    ok: bool
    rendered_path: Optional[str]
    render_error: Optional[str]
    flags: list[QcFlag] = field(default_factory=list)
    thumbnails: list[str] = field(default_factory=list)
    audio_summary: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "rendered_path": self.rendered_path,
            "render_error": self.render_error,
            "flags": [
                {"kind": f.kind, "start_sec": f.start_sec, "end_sec": f.end_sec, "detail": f.detail}
                for f in self.flags
            ],
            "thumbnails": self.thumbnails,
            "audio_summary": self.audio_summary,
        }


def qc_check(
    kdenlive_path: str,
    proxy_path: str,
    in_sec: float = 0.0,
    out_sec: float = 0.0,
    thumbnail_dir: str = "/tmp",
    take_thumbnails: bool = True,
) -> QcReport:
    """Render a ranged proxy, then run deterministic checks.

    If deterministic checks flag anything and ``take_thumbnails`` is True,
    a thumbnail is pulled for each flagged timestamp so the LLM can do a
    quick visual check. The thumbnails are written into ``thumbnail_dir``.
    """
    if out_sec <= in_sec:
        # Default: render the whole project.
        rr = render(kdenlive_path, proxy_path, mode="proxy")
    else:
        rr = render(kdenlive_path, proxy_path, mode="proxy", in_sec=in_sec, out_sec=out_sec)
    report = QcReport(
        ok=rr.ok,
        rendered_path=rr.output_path if rr.ok else None,
        render_error=rr.error,
    )
    if not rr.ok:
        return report

    # Deterministic checks.
    blacks = black_frames.list_black_frames(rr.output_path, in_sec=in_sec, out_sec=out_sec)
    for sp in blacks.spans:
        report.flags.append(QcFlag(
            kind="black", start_sec=sp.start_sec, end_sec=sp.end_sec,
            detail=f"black frame for {sp.duration_sec:.2f}s",
        ))
    silences = audio.list_silence(rr.output_path, in_sec=in_sec, out_sec=out_sec)
    for sp in silences.spans:
        report.flags.append(QcFlag(
            kind="silence", start_sec=sp.start_sec, end_sec=sp.end_sec,
            detail=f"silence for {sp.duration_sec:.2f}s (below {silences.threshold_db} dB)",
        ))
    levels = audio.get_audio_levels(rr.output_path, in_sec=in_sec, out_sec=out_sec)
    if levels.ok:
        report.audio_summary = f"rms={levels.rms_db:.1f} dB, peak={levels.peak_db:.1f} dB"
        if levels.peak_db < -50:
            report.flags.append(QcFlag(
                kind="low_audio", start_sec=in_sec, end_sec=out_sec,
                detail=f"peak only {levels.peak_db:.1f} dB — clip is effectively silent",
            ))

    if take_thumbnails and report.flags:
        for i, f in enumerate(report.flags):
            ts = (f.start_sec + f.end_sec) / 2.0
            out = f"{thumbnail_dir.rstrip('/')}/qc_thumb_{i}.jpg"
            res = get_thumbnail(rr.output_path, ts, out)
            if res.ok:
                report.thumbnails.append(res.output_path)

    return report
