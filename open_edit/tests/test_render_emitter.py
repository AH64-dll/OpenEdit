"""Unit tests for 30ms audio micro-fades in MLT Emitter."""
import pytest
from lxml import etree

from open_edit.ir.types import Timeline, Track, Clip, Effect
from open_edit.render.emitter import emit_timeline, EmitterConfig


def test_emitter_audio_micro_fades_regular_clip() -> None:
    clip = Clip(
        clip_id="c1",
        track_id="t1",
        track_kind="video",
        asset_hash="asset1",
        in_point_sec=0.0,
        out_point_sec=2.0,
        position_sec=0.0,
    )
    timeline = Timeline(duration_sec=2.0, tracks=[Track(track_id="t1", kind="video", clips=[clip])])
    config = EmitterConfig(profile={"width": 1920, "height": 1080, "frame_rate_num": 30, "frame_rate_den": 1})

    xml_str = emit_timeline(timeline, config)
    root = etree.fromstring(xml_str.encode("utf-8"))

    filter_el = root.find(".//playlist/entry/filter[@service='volume']")
    assert filter_el is not None, "Volume filter for micro-fade not found"
    assert filter_el.attrib.get("id") == "microfade_c1"

    kfs = filter_el.findall("kf")
    assert len(kfs) == 4
    for kf in kfs:
        assert kf.attrib.get("interp") == "linear", "Keyframe missing interp='linear' attribute"
    kf_data = [(kf.attrib["frame"], kf.attrib["value"]) for kf in kfs]
    assert kf_data == [
        ("0", "0.0"),
        ("1", "1.0"),
        ("59", "1.0"),
        ("60", "0.0"),
    ]


def test_emitter_audio_micro_fades_at_60fps() -> None:
    clip = Clip(
        clip_id="c1",
        track_id="t1",
        track_kind="video",
        asset_hash="asset1",
        in_point_sec=0.0,
        out_point_sec=2.0,
        position_sec=0.0,
    )
    timeline = Timeline(duration_sec=2.0, tracks=[Track(track_id="t1", kind="video", clips=[clip])])
    config = EmitterConfig(profile={"width": 1920, "height": 1080, "frame_rate_num": 60, "frame_rate_den": 1})

    xml_str = emit_timeline(timeline, config)
    root = etree.fromstring(xml_str.encode("utf-8"))

    filter_el = root.find(".//playlist/entry/filter[@id='microfade_c1']")
    assert filter_el is not None

    kfs = filter_el.findall("kf")
    assert len(kfs) == 4
    for kf in kfs:
        assert kf.attrib.get("interp") == "linear"
    kf_data = [(kf.attrib["frame"], kf.attrib["value"]) for kf in kfs]
    assert kf_data == [
        ("0", "0.0"),
        ("2", "1.0"),
        ("118", "1.0"),
        ("120", "0.0"),
    ]


def test_emitter_audio_micro_fades_short_clip_under_60ms() -> None:
    clip = Clip(
        clip_id="c_short",
        track_id="t1",
        track_kind="audio",
        asset_hash="asset_short",
        in_point_sec=0.0,
        out_point_sec=0.040,
        position_sec=0.0,
    )
    timeline = Timeline(duration_sec=0.040, tracks=[Track(track_id="t1", kind="audio", clips=[clip])])
    config = EmitterConfig(profile={"width": 1920, "height": 1080, "frame_rate_num": 30, "frame_rate_den": 1})

    xml_str = emit_timeline(timeline, config)
    root = etree.fromstring(xml_str.encode("utf-8"))

    filter_el = root.find(".//playlist/entry/filter[@id='microfade_c_short']")
    assert filter_el is not None

    kfs = filter_el.findall("kf")
    for kf in kfs:
        assert kf.attrib.get("interp") == "linear"

    kf_data = [(kf.attrib["frame"], kf.attrib["value"]) for kf in kfs]
    # At 30fps, 40ms clip fade duration is 20ms.
    # frame_0=0 (0.0), frame 1 is fade peak (1.0) and end frame.
    # Deduplication must preserve peak 1.0 so short clip is NOT muted!
    assert kf_data == [("0", "0.0"), ("1", "1.0")]
    assert kf_data != [("0", "0.0"), ("1", "0.0")], "Short clip must not be completely muted"
    values = [float(v) for _, v in kf_data]
    assert max(values) == 1.0, "Peak volume 1.0 must be present"


def test_emitter_audio_micro_fades_50ms_clip_at_60fps() -> None:
    clip = Clip(
        clip_id="c_50ms",
        track_id="t1",
        track_kind="audio",
        asset_hash="asset_50ms",
        in_point_sec=0.0,
        out_point_sec=0.050,
        position_sec=0.0,
    )
    timeline = Timeline(duration_sec=0.050, tracks=[Track(track_id="t1", kind="audio", clips=[clip])])
    config = EmitterConfig(profile={"width": 1920, "height": 1080, "frame_rate_num": 60, "frame_rate_den": 1})

    xml_str = emit_timeline(timeline, config)
    root = etree.fromstring(xml_str.encode("utf-8"))

    filter_el = root.find(".//playlist/entry/filter[@id='microfade_c_50ms']")
    assert filter_el is not None

    kfs = filter_el.findall("kf")
    for kf in kfs:
        assert kf.attrib.get("interp") == "linear"
    kf_data = [(kf.attrib["frame"], kf.attrib["value"]) for kf in kfs]
    # At 60fps, 50ms clip fade duration is 25ms.
    # frame_0=0 (0.0), frame 2 (1.0), frame 3 (0.0).
    assert kf_data == [("0", "0.0"), ("2", "1.0"), ("3", "0.0")]
    values = [float(v) for _, v in kf_data]
    assert max(values) == 1.0


def test_emitter_audio_micro_fades_1frame_clip() -> None:
    clip = Clip(
        clip_id="c_1frame",
        track_id="t1",
        track_kind="audio",
        asset_hash="asset_1frame",
        in_point_sec=0.0,
        out_point_sec=0.010,  # 10ms (< 1 frame at 30fps -> clip_end_frame == 0)
        position_sec=0.0,
    )
    timeline = Timeline(duration_sec=0.010, tracks=[Track(track_id="t1", kind="audio", clips=[clip])])
    config = EmitterConfig(profile={"width": 1920, "height": 1080, "frame_rate_num": 30, "frame_rate_den": 1})

    xml_str = emit_timeline(timeline, config)
    root = etree.fromstring(xml_str.encode("utf-8"))

    filter_el = root.find(".//playlist/entry/filter[@id='microfade_c_1frame']")
    assert filter_el is not None

    kfs = filter_el.findall("kf")
    assert len(kfs) == 1
    assert kfs[0].attrib.get("interp") == "linear"
    kf_data = [(kf.attrib["frame"], kf.attrib["value"]) for kf in kfs]
    # 1-frame clip must set volume to 1.0 (not muted)
    assert kf_data == [("0", "1.0")]


def test_emitter_audio_micro_fades_opt_out() -> None:
    clip = Clip(
        clip_id="c1",
        track_id="t1",
        track_kind="video",
        asset_hash="asset1",
        in_point_sec=0.0,
        out_point_sec=2.0,
        position_sec=0.0,
    )
    timeline = Timeline(duration_sec=2.0, tracks=[Track(track_id="t1", kind="video", clips=[clip])])
    config = EmitterConfig(enable_audio_micro_fades=False)

    xml_str = emit_timeline(timeline, config)
    root = etree.fromstring(xml_str.encode("utf-8"))

    filter_el = root.find(".//playlist/entry/filter[@id='microfade_c1']")
    assert filter_el is None, "Micro-fade filter should not be generated when disabled in config"


def test_emitter_audio_micro_fades_coexist_with_user_effects() -> None:
    user_effect = Effect(
        effect_id="eff_user_gain",
        effect_type="volume",
        params={"gain": 0.8},
    )
    clip = Clip(
        clip_id="c_user",
        track_id="t1",
        track_kind="audio",
        asset_hash="asset1",
        in_point_sec=0.0,
        out_point_sec=2.0,
        position_sec=0.0,
        effects=[user_effect],
    )
    timeline = Timeline(duration_sec=2.0, tracks=[Track(track_id="t1", kind="audio", clips=[clip])])
    config = EmitterConfig(enable_audio_micro_fades=True)

    xml_str = emit_timeline(timeline, config)
    root = etree.fromstring(xml_str.encode("utf-8"))

    filters = root.findall(".//playlist/entry/filter")
    assert len(filters) == 2
    filter_ids = [f.attrib.get("id") for f in filters]
    assert "microfade_c_user" in filter_ids
    assert "eff_user_gain" in filter_ids
