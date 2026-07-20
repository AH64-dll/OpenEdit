"""Phase 4.5 W8: long-form stress test (5-min synthetic video).

Per phase4-design-revised.md §6 + §9.8: validate the 11-min video claim.

End-to-end pipeline on a synthetic 5-min, 50-narrative-beat asset:

  ingest → silence cut → narrative analyze → motion graphics (templated, see
  note) → music → SFX → render → QC

Budget: <15 min wall clock on CI. Edit graph < 500 ops. No rate-limit
failures (all skills run in their rule-based / deterministic modes; no
LLM calls).

Note: motion graphics (W7) is not run inside this stress test because the
render sandbox is heavy. The render + templated motion graphics path is
covered separately in tests/test_skill/test_motion_graphics_templated.py
and tests/test_e2e_render.py.
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


@pytest.mark.timeout(_LONG_FORM_TIMEOUT_S)
def test_long_form_5min_video_end_to_end(tmp_path) -> None:
    """End-to-end: ingest + analyze + propose cuts + music + SFX + persist."""
    start = time.time()
    workdir = tmp_path / "long_form"
    workdir.mkdir()

    # Step 0: synthetic ingest. The asset is constructed in-memory; we don't
    # need to actually hash a real media file or call ffprobe. The downstream
    # skills all consume the Asset model directly.
    asset = _make_synthetic_5min_asset()
    edit_graph = EditGraphStore(workdir / "edit_graph.db")

    # Step 1: narrative analysis (rule-based; fast, no LLM).
    segments = analyze(asset, use_llm=False)
    assert len(segments) >= 10, (
        f"Expected >=10 narrative segments in 5 min, got {len(segments)}"
    )

    # Step 2: silence cuts. The synthetic data has 49 inter-beat gaps of 5s
    # each, all above the 400ms threshold, plus 50 zero-length intra-beat
    # gaps that don't qualify.
    gaps = find_silence_gaps(asset.alignment, threshold_ms=400)
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
    music_ops = select(segments, library)
    assert len(music_ops) >= 10, (
        f"Expected >=10 music ops (one per segment), got {len(music_ops)}"
    )
    assert len(music_ops) == len(segments)

    # Step 4: SFX placement (deterministic; one per beat transition).
    sfx_library = [
        SfxClip(sfx_id="whoosh_01", kind="whoosh", duration_s=0.5),
        SfxClip(sfx_id="impact_01", kind="impact", duration_s=0.3),
    ]
    sfx_ops = place(segments, music_downbeats=[], library=sfx_library)
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

    elapsed = time.time() - start
    assert elapsed < _LONG_FORM_TIMEOUT_S, (
        f"Pipeline took {elapsed:.1f}s, exceeds {_LONG_FORM_TIMEOUT_S}s budget"
    )
