"""Functional success-path checks for creative TOOL_TABLE wrappers.

The expensive render/analysis engines are mocked, but each wrapper is invoked
with valid inputs and its structured output is asserted.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from open_edit.agent.tools.pyagent_analyze_narrative import analyze_narrative
from open_edit.agent.tools.pyagent_generate_visual_for_segment import (
    generate_visual_for_segment,
)
from open_edit.agent.tools.pyagent_get_transcript_packed import get_transcript_packed
from open_edit.agent.tools.pyagent_place_sfx import place_sfx
from open_edit.agent.tools.pyagent_select_music import select_music


def _asset():
    return SimpleNamespace(alignment=[{"word": "hello"}], asset_hash="asset-a")


def test_analyze_and_pack_transcript_success(tmp_path):
    segment = SimpleNamespace(model_dump=lambda: {"beat_type": "hook"})
    with (
        mock.patch(
            "open_edit.agent.tools._contract.get_asset_or_error",
            return_value=(_asset(), None),
        ),
        mock.patch(
            "open_edit.agent.tools.pyagent_analyze_narrative.get_asset_or_error",
            return_value=(_asset(), None),
        ),
        mock.patch(
            "open_edit.agent.tools.pyagent_get_transcript_packed.get_asset_or_error",
            return_value=(_asset(), None),
        ),
        mock.patch(
            "open_edit.agent.skills.narrative_analyzer.analyze",
            return_value=[segment],
        ),
        mock.patch(
            "open_edit.agent.tools.pyagent_get_transcript_packed.pack_transcript",
            return_value="hello",
        ),
    ):
        narrative = analyze_narrative({"asset_hash": "asset-a"}, str(tmp_path))
        transcript = get_transcript_packed({"asset_hash": "asset-a"}, str(tmp_path))
    assert narrative == {"status": "ok", "segments": [{"beat_type": "hook"}]}
    assert transcript["status"] == "ok"
    assert transcript["transcript_packed"] == "hello"


def test_music_and_sfx_wrappers_return_ops(tmp_path):
    segment = SimpleNamespace(model_dump=lambda: {"beat_type": "hook"})
    with (
        mock.patch(
            "open_edit.agent.tools._contract.get_asset_or_error",
            return_value=(_asset(), None),
        ),
        mock.patch(
            "open_edit.agent.tools.pyagent_select_music.get_asset_or_error",
            return_value=(_asset(), None),
        ),
        mock.patch(
            "open_edit.agent.tools.pyagent_place_sfx.get_asset_or_error",
            return_value=(_asset(), None),
        ),
        mock.patch(
            "open_edit.agent.skills.narrative_analyzer.analyze",
            return_value=[segment],
        ),
        mock.patch(
            "open_edit.agent.skills.music_selector.select",
            return_value=[],
        ),
        mock.patch(
            "open_edit.agent.skills.sfx_placer.place",
            return_value=[],
        ),
    ):
        music = select_music({"asset_hash": "asset-a"}, str(tmp_path))
        sfx = place_sfx({"asset_hash": "asset-a"}, str(tmp_path))
    assert music == {"status": "ok", "ops": []}
    assert sfx["status"] == "ok"
    assert sfx["timing"]["mode"] == "narrative_transition"


def test_generate_visual_wrapper_returns_operation(tmp_path):
    segment = SimpleNamespace(beat_type="hook")
    operation = SimpleNamespace(model_dump=lambda: {"kind": "add_clip"})
    with (
        mock.patch(
            "open_edit.agent.tools._contract.get_asset_or_error",
            return_value=(_asset(), None),
        ),
        mock.patch(
            "open_edit.agent.tools.pyagent_generate_visual_for_segment.get_asset_or_error",
            return_value=(_asset(), None),
        ),
        mock.patch(
            "open_edit.agent.skills.narrative_analyzer.analyze",
            return_value=[segment],
        ),
        mock.patch(
            "open_edit.agent.skills.motion_graphics.engine.generate_visual",
            return_value=operation,
        ),
    ):
        result = generate_visual_for_segment(
            {
                "asset_hash": "asset-a",
                "beat_type": "hook",
                "template": "title_card",
                "project_id": "p",
            },
            str(tmp_path),
        )
    assert result == {"status": "ok", "op": {"kind": "add_clip"}}
