"""Tests for AddHtmlOverlayOp and RemoveHtmlOverlayOp IR operations."""
from __future__ import annotations

import pytest

from open_edit.ir.types import (
    AddHtmlOverlayOp,
    HtmlOverlay,
    Project,
    RemoveHtmlOverlayOp,
    Timeline,
)
from open_edit.ir.apply import apply_operation, derive_timeline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_project(*ops) -> Project:
    return Project(name="test", edit_graph=list(ops))


def _overlay_op(**kwargs) -> AddHtmlOverlayOp:
    defaults = dict(
        author="ai",
        template_path="templates/lower_third.html",
        position_sec=5.0,
        duration_sec=3.0,
    )
    defaults.update(kwargs)
    return AddHtmlOverlayOp(**defaults)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestAddHtmlOverlayOpValidation:
    def test_valid_op_creates_correctly(self):
        op = _overlay_op()
        assert op.kind == "add_html_overlay"
        assert op.template_path == "templates/lower_third.html"
        assert op.position_sec == 5.0
        assert op.duration_sec == 3.0
        assert op.variables == {}
        assert op.overlay_id  # auto-generated UUID

    def test_variables_are_stored(self):
        op = _overlay_op(variables={"title": "Hello", "color": "#FF0000"})
        assert op.variables["title"] == "Hello"
        assert op.variables["color"] == "#FF0000"

    def test_overlay_id_is_unique(self):
        op1 = _overlay_op()
        op2 = _overlay_op()
        assert op1.overlay_id != op2.overlay_id

    def test_custom_overlay_id_preserved(self):
        op = _overlay_op(overlay_id="my-custom-id")
        assert op.overlay_id == "my-custom-id"

    def test_status_defaults_to_applied(self):
        op = _overlay_op()
        assert op.status == "applied"

    def test_author_field_required(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            AddHtmlOverlayOp(
                template_path="t.html",
                position_sec=0.0,
                duration_sec=1.0,
                # author missing
            )


# ---------------------------------------------------------------------------
# apply_operation: AddHtmlOverlayOp
# ---------------------------------------------------------------------------

class TestApplyAddHtmlOverlay:
    def test_overlay_added_to_timeline(self):
        timeline = Timeline()
        op = _overlay_op(position_sec=2.0, duration_sec=4.0)
        result = apply_operation(timeline, op)
        assert len(result.overlays) == 1
        ov = result.overlays[0]
        assert ov.template_path == "templates/lower_third.html"
        assert ov.position_sec == 2.0
        assert ov.duration_sec == 4.0

    def test_multiple_overlays_sorted_by_position(self):
        timeline = Timeline()
        op1 = _overlay_op(position_sec=10.0, duration_sec=2.0)
        op2 = _overlay_op(position_sec=3.0, duration_sec=1.0)
        op3 = _overlay_op(position_sec=7.0, duration_sec=1.5)
        timeline = apply_operation(timeline, op1)
        timeline = apply_operation(timeline, op2)
        timeline = apply_operation(timeline, op3)
        positions = [o.position_sec for o in timeline.overlays]
        assert positions == sorted(positions)

    def test_reverted_op_not_applied(self):
        timeline = Timeline()
        op = _overlay_op()
        op = op.model_copy(update={"status": "reverted"})
        result = apply_operation(timeline, op)
        assert len(result.overlays) == 0

    def test_variables_propagated_to_overlay(self):
        timeline = Timeline()
        op = _overlay_op(variables={"name": "Alice", "title": "Engineer"})
        result = apply_operation(timeline, op)
        assert result.overlays[0].variables == {"name": "Alice", "title": "Engineer"}


# ---------------------------------------------------------------------------
# apply_operation: RemoveHtmlOverlayOp
# ---------------------------------------------------------------------------

class TestApplyRemoveHtmlOverlay:
    def test_remove_existing_overlay(self):
        timeline = Timeline()
        add_op = _overlay_op(overlay_id="ov-1")
        timeline = apply_operation(timeline, add_op)
        assert len(timeline.overlays) == 1

        remove_op = RemoveHtmlOverlayOp(author="user", overlay_id="ov-1")
        timeline = apply_operation(timeline, remove_op)
        assert len(timeline.overlays) == 0

    def test_remove_nonexistent_overlay_is_noop(self):
        timeline = Timeline()
        remove_op = RemoveHtmlOverlayOp(author="user", overlay_id="does-not-exist")
        result = apply_operation(timeline, remove_op)
        assert len(result.overlays) == 0

    def test_remove_only_target_overlay(self):
        timeline = Timeline()
        op1 = _overlay_op(overlay_id="keep-me", position_sec=0.0)
        op2 = _overlay_op(overlay_id="remove-me", position_sec=5.0)
        timeline = apply_operation(timeline, op1)
        timeline = apply_operation(timeline, op2)
        assert len(timeline.overlays) == 2

        remove_op = RemoveHtmlOverlayOp(author="user", overlay_id="remove-me")
        timeline = apply_operation(timeline, remove_op)
        assert len(timeline.overlays) == 1
        assert timeline.overlays[0].overlay_id == "keep-me"


# ---------------------------------------------------------------------------
# derive_timeline: overlays affect duration_sec
# ---------------------------------------------------------------------------

class TestDeriveTimelineWithOverlays:
    def test_overlay_duration_extends_timeline(self):
        """An overlay ending at t=12 should push duration_sec to at least 12."""
        op = _overlay_op(position_sec=10.0, duration_sec=2.0)
        project = _base_project(op)
        timeline = derive_timeline(project)
        assert timeline.duration_sec >= 12.0

    def test_overlay_does_not_shorten_clip_dominated_duration(self):
        """If clips end later than overlays, duration_sec reflects the clips."""
        from open_edit.ir.types import AddClipOp
        clip_op = AddClipOp(
            author="ai",
            asset_hash="abc123",
            track_id="video_1",
            position_sec=0.0,
            in_point_sec=0.0,
            out_point_sec=30.0,
        )
        overlay_op = _overlay_op(position_sec=0.0, duration_sec=5.0)
        project = _base_project(clip_op, overlay_op)
        timeline = derive_timeline(project)
        assert timeline.duration_sec >= 30.0

    def test_reverted_overlay_excluded_from_derive(self):
        op = _overlay_op(position_sec=50.0, duration_sec=10.0)
        op = op.model_copy(update={"status": "reverted"})
        project = _base_project(op)
        timeline = derive_timeline(project)
        assert len(timeline.overlays) == 0
        assert timeline.duration_sec == 0.0

    def test_add_then_remove_overlay_leaves_empty(self):
        add_op = _overlay_op(overlay_id="ov-x", position_sec=5.0, duration_sec=3.0)
        remove_op = RemoveHtmlOverlayOp(author="user", overlay_id="ov-x")
        project = _base_project(add_op, remove_op)
        timeline = derive_timeline(project)
        assert len(timeline.overlays) == 0

    def test_multiple_overlays_all_present_in_derived_timeline(self):
        ops = [
            _overlay_op(position_sec=float(i), duration_sec=1.0)
            for i in range(5)
        ]
        project = _base_project(*ops)
        timeline = derive_timeline(project)
        assert len(timeline.overlays) == 5
