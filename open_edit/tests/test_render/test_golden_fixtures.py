"""Tests for the hand-constructed 11-clip / 10-transition golden fixture."""
import json
from pathlib import Path

import pytest

from open_edit.ir.types import Project, OperationUnion
from open_edit.pydantic_compat import TypeAdapter


GOLDEN_DIR = Path(__file__).parent.parent / "testdata" / "golden_11clip"


def test_golden_edit_graph_loads() -> None:
    """The hand-constructed edit graph is a valid Project."""
    payload = json.loads((GOLDEN_DIR / "edit_graph.json").read_text())
    project = TypeAdapter(Project).validate_python(payload)
    assert len(project.edit_graph) > 0


def test_golden_has_11_clips_and_10_transitions() -> None:
    payload = json.loads((GOLDEN_DIR / "edit_graph.json").read_text())
    project = TypeAdapter(Project).validate_python(payload)
    from open_edit.ir.types import AddClipOp, AddTransitionOp
    clips = [op for op in project.edit_graph if isinstance(op, AddClipOp)]
    transitions = [op for op in project.edit_graph if isinstance(op, AddTransitionOp)]
    assert len(clips) == 11
    assert len(transitions) == 10


def test_golden_transitions_references_valid_clips() -> None:
    """Each transition's clip_a_id and clip_b_id must be a real clip_id."""
    payload = json.loads((GOLDEN_DIR / "edit_graph.json").read_text())
    project = TypeAdapter(Project).validate_python(payload)
    from open_edit.ir.types import AddClipOp, AddTransitionOp
    clip_ids = {op.clip_id for op in project.edit_graph if isinstance(op, AddClipOp)}
    for t in project.edit_graph:
        if isinstance(t, AddTransitionOp):
            assert t.clip_a_id in clip_ids, f"transition references unknown clip_a_id {t.clip_a_id}"
            assert t.clip_b_id in clip_ids, f"transition references unknown clip_b_id {t.clip_b_id}"


def test_golden_expected_timeline_matches_derive() -> None:
    """Deriving the timeline from the edit graph produces a Timeline with
    11 clips across 1 video track."""
    payload = json.loads((GOLDEN_DIR / "edit_graph.json").read_text())
    project = TypeAdapter(Project).validate_python(payload)
    from open_edit.ir.apply import derive_timeline
    timeline = derive_timeline(project)
    assert len(timeline.tracks) == 1
    assert len(timeline.tracks[0].clips) == 11
