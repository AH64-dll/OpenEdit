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
    # With the default (gpu) backend the vcodec is resolved to a hardware
    # encoder when available (nvenc/amf/qsv/vaapi), so pin backend="cpu" for
    # a deterministic libx264 assertion.
    args = profile_to_mlt_args(p, backend="cpu")
    assert "vcodec=libx264" in args
    assert "acodec=aac" in args
    assert "s=1920x1080" in args
    assert "frame_rate_num=30" in args
    assert "frame_rate_den=1" in args
    assert "progressive=1" in args
    # The gpu path still emits a vcodec entry (hardware encoder or libx264
    # fallback) — the codec arg must never be dropped.
    gpu_args = profile_to_mlt_args(p, backend="gpu")
    assert any(a.startswith("vcodec=") for a in gpu_args)


def test_profile_to_mlt_args_includes_aspect_and_colorspace() -> None:
    p = select_profile("720p30")
    args = profile_to_mlt_args(p)
    assert "sample_aspect_num=1" in args
    assert "sample_aspect_den=1" in args
    assert "display_aspect_num=16" in args
    assert "display_aspect_den=9" in args
    assert "colorspace=709" in args


"""Quality fields, resolution, fingerprint."""
import pytest
from pydantic import ValidationError

from open_edit.render.profiles import (
    RenderProfile, profile_fingerprint, profile_with_quality,
    resolve_encoder_args, select_profile,
)


@pytest.fixture(autouse=True)
def _probe_all_encoders(monkeypatch):
    """Make encoder probing deterministic regardless of host hardware."""
    from open_edit.render import encoder as enc

    monkeypatch.setattr(enc, "_probe_encoder", lambda vcodec, extra: True)


def test_profile_with_quality_defaults_by_mode():
    p = profile_with_quality(None, "final")
    assert p.name == "1080p30" and p.quality == "standard"
    p2 = profile_with_quality(None, "proxy")
    assert p2.name == "720p30" and p2.quality == "fast"


def test_profile_with_quality_applies_overrides():
    p = profile_with_quality(None, "final", quality="high", overrides={"crf": 20})
    assert p.quality == "high" and p.crf == 20


def test_profile_validation_rejects_bad_values():
    with pytest.raises(ValidationError):
        RenderProfile(name="x", width=1, height=1, frame_rate_num=30,
                      frame_rate_den=1, quality="bogus")
    with pytest.raises(ValidationError):
        RenderProfile(name="x", width=1, height=1, frame_rate_num=30,
                      frame_rate_den=1, crf=99)
    with pytest.raises(ValidationError):
        RenderProfile(name="x", width=1, height=1, frame_rate_num=30,
                      frame_rate_den=1, codec="vp9")
    with pytest.raises(ValidationError):
        RenderProfile(name="x", width=1, height=1, frame_rate_num=30,
                      frame_rate_den=1, scale="1080px")


def test_resolve_encoder_args_standard_final_matches_legacy():
    p = profile_with_quality(None, "final")          # standard
    spec = resolve_encoder_args(p, "gpu")
    assert spec.vcodec == "h264_nvenc"
    assert "b=10M" in spec.melt_args


def test_fingerprint_differs_when_quality_differs():
    a = profile_fingerprint(profile_with_quality(None, "final", quality="fast"), "gpu")
    b = profile_fingerprint(profile_with_quality(None, "final", quality="standard"), "gpu")
    assert a != b
