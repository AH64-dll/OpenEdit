"""Phase 4.5 W8: long-form stress test (5-min synthetic video).

Per phase4-design-revised.md §6 + §9.8: validate the 11-min video claim.

End-to-end pipeline on a synthetic 5-min, 50-narrative-beat asset:

  ingest → silence cut → narrative analyze → motion graphics (skipped) →
  music → SFX → render (skipped) → QC (skipped)

Stages intentionally skipped in this stress test (each has its own
dedicated, heavier test):

- **ingest** — we construct the synthetic ``Asset`` in-memory rather than
  calling ``AssetStore.ingest_paths()`` (which requires real media +
  ffprobe + Whisper). Ingest path is covered in ``tests/test_storage/``.
- **motion graphics (W7)** — render sandbox is heavy; covered in
  ``tests/test_skill/test_motion_graphics_templated.py``.
- **render** — covered in ``tests/test_e2e_render.py`` and
  ``tests/test_render/``.
- **QC** — covered in ``tests/test_qc/``.

Budget: <15 min wall clock on CI. Edit graph < 500 ops. No rate-limit
failures (all skills run in their rule-based / deterministic modes; no
LLM or network calls, so the rate-limit check is vacuous by
construction — but the assertion documents the contract).
"""
import time

import pytest

from open_edit.agent.skills.music_selector import MusicTrack, select
from open_edit.agent.skills.narrative_analyzer import analyze
from open_edit.agent.skills.sfx_placer import SfxClip, place
from open_edit.agent.skills.silence_cutter import find_silence_gaps
from open_edit.ir.types import Asset, WordAlignment
from open_edit.storage.edit_graph import EditGraphStore


# 15-minute wall-clock budget for the long-form pipeline (per §6 + §9.8).
_LONG_FORM_TIMEOUT_S = 900

# Edit-graph cap from §6: "edit graph <500 ops" for the 11-min video claim.
# A 5-min synthetic stress test must stay well under that.
_EDIT_GRAPH_OP_CAP = 500


def _make_synthetic_5min_asset() -> Asset:
    """Generate a 5-min synthetic asset with 50 narrative beats.

    Beats are 6s wide with 1s of in-beat word coverage and 5s of inter-beat
    silence. That gives us 49 inter-beat silence gaps of 5s each, which
    exercises find_silence_gaps with a 400ms threshold.
    """
    alignment: list[WordAlignment] = []
    for i in range(50):
        t_start = i * 6.0
        for j in range(2):
            alignment.append(WordAlignment(
                word=f"word{i}_{j}",
                t_start=t_start + j * 0.5,
                t_end=t_start + (j + 1) * 0.5,
                confidence=1.0,
            ))
    return Asset(
        asset_hash="synthetic_5min",
        original_path="/tmp/synthetic.mp4",
        stored_path="/tmp/synthetic.mp4",
        type="video",
        duration_sec=300.0,
        fps=30.0, width=1920, height=1080, codec="h264", has_audio=True,
        alignment=alignment,
    )


def _is_rate_limit_error(exc: BaseException) -> bool:
    """Return True if ``exc`` (or any chained cause) looks like a rate-limit failure."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        msg = str(current).lower()
        if "rate limit" in msg or "rate-limit" in msg or "too many requests" in msg or "http 429" in msg:
            return True
        current = current.__cause__ or current.__context__
    return False


@pytest.mark.timeout(_LONG_FORM_TIMEOUT_S)
def test_long_form_5min_video_end_to_end(tmp_path) -> None:
    """End-to-end: ingest + analyze + propose cuts + music + SFX + persist."""
    start = time.time()
    workdir = tmp_path / "long_form"
    workdir.mkdir()

    # Track any exception raised by a skill call so the post-pipeline
    # assertions can include an explicit "no rate-limit failures" check
    # (the v1 test makes no LLM/network calls, so this is vacuous by
    # construction — but the assertion documents the §6 contract).
    caught_exceptions: list[BaseException] = []

    # Step 0: synthetic ingest. The asset is constructed in-memory; we don't
    # need to actually hash a real media file or call ffprobe. The downstream
    # skills all consume the Asset model directly.
    asset = _make_synthetic_5min_asset()
    edit_graph = EditGraphStore(workdir / "edit_graph.db")

    # Step 1: narrative analysis (rule-based; fast, no LLM).
    try:
        segments = analyze(asset, use_llm=False)
    except BaseException as exc:
        caught_exceptions.append(exc)
        raise
    assert len(segments) >= 10, (
        f"Expected >=10 narrative segments in 5 min, got {len(segments)}"
    )

    # Step 2: silence cuts. The synthetic data has 49 inter-beat gaps of 5s
    # each, all above the 400ms threshold, plus 50 zero-length intra-beat
    # gaps that don't qualify.
    try:
        gaps = find_silence_gaps(asset.alignment, threshold_ms=400)
    except BaseException as exc:
        caught_exceptions.append(exc)
        raise
    assert len(gaps) == 49, (
        f"Expected 49 inter-beat silence gaps, got {len(gaps)}"
    )
    for gap_start, gap_end in gaps:
        assert gap_end - gap_start >= 0.4

    # Step 3: music selection (deterministic; uses bundled BEAT_MOOD_MAP).
    library = [
        MusicTrack(track_id="upbeat_01", mood="upbeat", bpm=120, energy=0.8),
        MusicTrack(track_id="contemplative_01", mood="contemplative", bpm=70, energy=0.3),
    ]
    try:
        music_ops = select(segments, library)
    except BaseException as exc:
        caught_exceptions.append(exc)
        raise
    assert len(music_ops) >= 10, (
        f"Expected >=10 music ops (one per segment), got {len(music_ops)}"
    )
    assert len(music_ops) == len(segments)

    # Step 4: SFX placement (deterministic; one per beat transition).
    sfx_library = [
        SfxClip(sfx_id="whoosh_01", kind="whoosh", duration_s=0.5),
        SfxClip(sfx_id="impact_01", kind="impact", duration_s=0.3),
    ]
    try:
        sfx_ops = place(segments, music_downbeats=[], library=sfx_library)
    except BaseException as exc:
        caught_exceptions.append(exc)
        raise
    assert len(sfx_ops) >= 5, (
        f"Expected >=5 sfx ops, got {len(sfx_ops)}"
    )
    assert len(sfx_ops) == len(segments) - 1

    # Step 5: persist all ops to the edit graph.
    for op in music_ops + sfx_ops:
        edit_graph.append(op)

    all_ops = edit_graph.load_all()
    assert len(all_ops) < _EDIT_GRAPH_OP_CAP, (
        f"Edit graph has {len(all_ops)} ops, exceeds cap of {_EDIT_GRAPH_OP_CAP}"
    )
    assert len(all_ops) == len(music_ops) + len(sfx_ops)

    # Explicit "no rate-limit failures" check from the brief (§6 / §9.8).
    # Vacuous by construction for v1 (no LLM/network calls), but documents
    # the contract so a future regression that introduces a network call
    # into the pipeline will surface here.
    rate_limit_failures = [e for e in caught_exceptions if _is_rate_limit_error(e)]
    assert rate_limit_failures == [], (
        f"Encountered {len(rate_limit_failures)} rate-limit failure(s): "
        f"{[str(e) for e in rate_limit_failures]}"
    )

    elapsed = time.time() - start
    assert elapsed < _LONG_FORM_TIMEOUT_S, (
        f"Pipeline took {elapsed:.1f}s, exceeds {_LONG_FORM_TIMEOUT_S}s budget"
    )
