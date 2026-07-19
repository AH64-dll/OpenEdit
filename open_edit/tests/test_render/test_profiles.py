"""Tests for render profile selection and MLT arg generation."""
import pytest

from open_edit.render.profiles import (
    DEFAULT_PROFILES,
    RenderProfile,
    profile_to_mlt_args,
    select_profile,
)


def test_default_profiles_includes_1080p30() -> None:
    names = [p.name for p in DEFAULT_PROFILES]
    assert "1080p30" in names


def test_default_profiles_includes_720p30() -> None:
    names = [p.name for p in DEFAULT_PROFILES]
    assert "720p30" in names


def test_select_profile_returns_named_profile() -> None:
    p = select_profile("1080p30")
    assert p.name == "1080p30"
    assert p.width == 1920
    assert p.height == 1080


def test_select_profile_unknown_raises() -> None:
    with pytest.raises(KeyError):
        select_profile("nope_8k_60")


def test_profile_to_mlt_args_includes_codecs() -> None:
    p = select_profile("1080p30")
    args = profile_to_mlt_args(p)
    assert "vcodec=libx264" in args
    assert "acodec=aac" in args
    assert "s=1920x1080" in args
    assert "frame_rate_num=30" in args
    assert "frame_rate_den=1" in args
    assert "progressive=1" in args


def test_profile_to_mlt_args_includes_aspect_and_colorspace() -> None:
    p = select_profile("720p30")
    args = profile_to_mlt_args(p)
    assert "sample_aspect_num=1" in args
    assert "sample_aspect_den=1" in args
    assert "display_aspect_num=16" in args
    assert "display_aspect_den=9" in args
    assert "colorspace=709" in args
