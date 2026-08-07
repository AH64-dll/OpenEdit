"""Regression checks for the timeline-test Remotion photo presentation."""

from pathlib import Path

from open_edit.ir.derive import derive_timeline
from open_edit.ir.types import Project
from open_edit.storage.edit_graph import EditGraphStore


FOCUS_POPUP_SOURCE = Path(
    "/home/ah64/OpenEditProjects/timeline-test/.open_edit/remotion/"
    "src/compositions/FocusPopup.tsx"
)
REMOTION_ROOT_SOURCE = FOCUS_POPUP_SOURCE.parents[1] / "Root.tsx"
EDIT_GRAPH = FOCUS_POPUP_SOURCE.parents[3] / "edit_graph.db"


def test_focus_popup_uses_intrinsic_image_bounds_without_phone_frame() -> None:
    if not FOCUS_POPUP_SOURCE.is_file():
        import pytest
        pytest.skip("timeline-test fixture is not installed")
    source = FOCUS_POPUP_SOURCE.read_text(encoding="utf-8")

    assert "cardWidthRatio" not in source
    assert "cardHeightRatio" not in source
    assert 'width: "100%"' not in source
    assert 'height: "100%"' not in source
    assert 'width: "auto"' in source
    assert 'height: "auto"' in source
    assert "maxWidth: width *" in source
    assert "maxHeight: height *" in source
    assert "boxShadow" not in source
    assert 'drop-shadow(' in source
    assert 'backgroundColor: "rgba(255, 255, 255, 0.98)"' not in source


def test_gemini_alias_registration_bumps_focus_popup_cache() -> None:
    if not FOCUS_POPUP_SOURCE.is_file() or not REMOTION_ROOT_SOURCE.is_file():
        import pytest
        pytest.skip("timeline-test fixture is not installed")
    root_source = REMOTION_ROOT_SOURCE.read_text(encoding="utf-8")

    assert 'photoLayoutVersion: "intrinsic-image-v3"' in root_source


def test_existing_photo_compositions_drop_legacy_card_ratios() -> None:
    if not EDIT_GRAPH.is_file():
        import pytest
        pytest.skip("timeline-test fixture is not installed")
    store = EditGraphStore(EDIT_GRAPH)
    timeline = derive_timeline(
        Project(
            project_id=store.project_id,
            name=EDIT_GRAPH.parent.name,
            edit_graph=store.load_all(),
        )
    )
    photo_compositions = (
        composition
        for composition in timeline.remotion_compositions
        if composition.composition_id in {"FocusPopup", "GeminiFocusPopup"}
    )
    for composition in photo_compositions:
        assert "cardWidthRatio" not in composition.props
        assert "cardHeightRatio" not in composition.props
