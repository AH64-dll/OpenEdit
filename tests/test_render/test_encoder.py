"""Quality tier model: default tiers are bit-identical to legacy args."""
import pytest

from open_edit.render.encoder import (
    TIERS, apply_overrides, select_encoder,
)


@pytest.fixture(autouse=True)
def _probe_all_encoders(monkeypatch):
    """Make encoder probing deterministic regardless of host hardware."""
    from open_edit.render import encoder as enc

    monkeypatch.setattr(enc, "_probe_encoder", lambda vcodec, extra: True)


def test_tiers_exist():
    assert TIERS == ("fast", "standard", "high", "archival")


def test_legacy_final_maps_to_standard():
    # final=True must equal old _SPECS final rows (bit-identical)
    assert select_encoder("gpu", final=True).vcodec == "h264_nvenc"
    spec = select_encoder("gpu", final=True)
    assert ("b=10M", "maxrate=14M") == (spec.melt_args[1], spec.melt_args[2])


def test_legacy_proxy_maps_to_fast():
    spec = select_encoder("gpu", final=False)
    assert spec.melt_args == ("rc=constqp", "cq=23", "preset=p4")


def test_cpu_default_unchanged():
    spec = select_encoder("cpu")
    assert spec.vcodec == "libx264"
    assert spec.melt_args == ("crf=23", "preset=veryfast")


def test_codec_override_hevc_cpu():
    spec = select_encoder("cpu", tier="standard", codec="hevc")
    assert spec.vcodec == "libx265"
    assert "-crf" in spec.ffmpeg_args and "24" in spec.ffmpeg_args


def test_codec_override_av1_cpu():
    spec = select_encoder("cpu", tier="standard", codec="av1")
    assert spec.vcodec == "libsvtav1"


def test_apply_overrides_appends_last_wins():
    spec = select_encoder("cpu", tier="standard")
    out = apply_overrides(spec, {"crf": 22, "preset": "slow"})
    assert out.ffmpeg_args[-4:] == ["-crf", "22", "-preset", "slow"]
    assert out.melt_args[-2:] == ("crf=22", "preset=slow")


def test_apply_overrides_nvenc_crf_uses_cq():
    spec = select_encoder("gpu", tier="standard")
    out = apply_overrides(spec, {"crf": 20})
    assert "-cq" in out.ffmpeg_args


def test_apply_overrides_empty_identity():
    spec = select_encoder("cpu", tier="high")
    assert apply_overrides(spec, {}) == spec
