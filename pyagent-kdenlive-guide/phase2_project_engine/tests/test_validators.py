import pytest
from phase2_project_engine.errors import ValidationError
from phase2_project_engine.validators import (
    validate_track_index, validate_position_sec, validate_clip_range,
    validate_transition_kind, validate_effect_id, validate_effect_params,
    validate_source_path, validate_marker_kind,
)


def test_validate_track_index_ok():
    validate_track_index(0, 4)  # no raise


def test_validate_track_index_out_of_range():
    with pytest.raises(ValidationError) as ei:
        validate_track_index(5, 4)
    assert "fix:" in str(ei.value)


def test_validate_position_sec_negative():
    with pytest.raises(ValidationError):
        validate_position_sec(-1.0)


def test_validate_clip_range_inverted():
    with pytest.raises(ValidationError) as ei:
        validate_clip_range(2.0, 1.0, 5.0)
    assert "fix:" in str(ei.value)


def test_validate_clip_range_out_of_bounds():
    with pytest.raises(ValidationError):
        validate_clip_range(0.0, 10.0, 5.0)


def test_validate_transition_kind_resolves():
    catalog = [
        {"kdenlive_id": "dissolve", "mlt_service": "mix", "name": "Dissolve"},
        {"kdenlive_id": "wipe", "mlt_service": "composite", "name": "Wipe"},
    ]
    assert validate_transition_kind("dissolve", catalog) == "dissolve"
    assert validate_transition_kind("DISSOLVE", catalog) == "dissolve"  # case
    with pytest.raises(ValidationError):
        validate_transition_kind("nope", catalog)


def test_validate_effect_id_unknown():
    with pytest.raises(ValidationError) as ei:
        validate_effect_id("nonexistent", [{"kdenlive_id": "blur"}])
    assert "fix:" in str(ei.value)


def test_validate_effect_params_type_coercion():
    entry = {
        "kdenlive_id": "blur",
        "parameters": [
            {"name": "sigma", "type": "double"},
            {"name": "enabled", "type": "bool"},
        ],
    }
    out = validate_effect_params(entry, {"sigma": "2.5", "enabled": "1"})
    assert out == {"sigma": "2.5", "enabled": "1"}


def test_validate_effect_params_rejects_unknown_name():
    entry = {"kdenlive_id": "blur", "parameters": [{"name": "sigma", "type": "double"}]}
    with pytest.raises(ValidationError):
        validate_effect_params(entry, {"unknown_param": "1"})


def test_validate_source_path_requires_existing_file(tmp_path):
    p = tmp_path / "a.mp4"
    p.write_bytes(b"x")
    out = validate_source_path(str(p))
    assert out == p
    with pytest.raises(ValidationError):
        validate_source_path("/nonexistent/file.mp4")


def test_validate_marker_kind_normalizes():
    assert validate_marker_kind("MARKER") == "marker"
    assert validate_marker_kind("guide") == "guide"
    with pytest.raises(ValidationError):
        validate_marker_kind("nope")
