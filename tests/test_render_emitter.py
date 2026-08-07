"""Unit tests for 30ms audio micro-fades in MLT Emitter."""
import pytest
from lxml import etree

from open_edit.ir.types import Timeline, Track, Clip, Effect
from open_edit.render.emitter import emit_timeline, EmitterConfig

def _level_keyframes(filter_el) -> list[tuple[str, str]]:
    """Parse the MLT animated property string (frame=value; ...) of a filter."""
    prop = filter_el.find("property[@name='level']")
    assert prop is not None, "volume filter missing <property name='level'>"
    parts = [x for x in prop.text.split(";") if x.strip()]
    return [tuple(x.strip().split("=")) for x in parts]  # type: ignore[return-value]




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

    filter_el = root.find(".//playlist/entry/filter[@id='microfade_c1']")
    assert filter_el is not None, "Volume filter for micro-fade not found"
    assert filter_el.attrib.get("id") == "microfade_c1"
    # MLT >= 7.22 loads filters via the mlt_service attribute
    assert filter_el.attrib.get("mlt_service") == "volume"

    kf_data = _level_keyframes(filter_el)
    assert kf_data == [
        ("0", "-80.0"),
        ("1", "0.0"),
        ("59", "0.0"),
        ("60", "-80.0"),
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

    kf_data = _level_keyframes(filter_el)
    assert kf_data == [
        ("0", "-80.0"),
        ("2", "0.0"),
        ("118", "0.0"),
        ("120", "-80.0"),
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

    kf_data = _level_keyframes(filter_el)
    # At 30fps, 40ms clip fade duration is 20ms.
    # frame_0=-80 dBFS (silence), frame 1 is fade peak (0 dBFS) and end frame.
    # Deduplication must preserve peak 0 dBFS so short clip is NOT muted!
    assert kf_data == [("0", "-80.0"), ("1", "0.0")]
    values = [float(v) for _, v in kf_data]
    assert max(values) == 0.0, "Peak volume 0 dBFS must be present"


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

    kf_data = _level_keyframes(filter_el)
    # At 60fps, 50ms clip fade duration is 25ms.
    # frame_0=-80 dBFS, frame 2 (0 dBFS), frame 3 (-80 dBFS).
    assert kf_data == [("0", "-80.0"), ("2", "0.0"), ("3", "-80.0")]
    values = [float(v) for _, v in kf_data]
    assert max(values) == 0.0


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

    kf_data = _level_keyframes(filter_el)
    # 1-frame clip must set volume to unity 0 dBFS (not muted)
    assert kf_data == [("0", "0.0")]


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


# =========================================================================
# MLT 7.22+ compatibility (mlt_service attribute, animated property strings)
# =========================================================================


def test_emitter_effect_uses_mlt_service_and_catalog_mapping() -> None:
    """Effects emit mlt_service (MLT >= 7.22) and catalog property mapping.

    The catalog maps agent-facing param names to real MLT properties
    (brightness.value -> level). Both the legacy ``service`` and the
    modern ``mlt_service`` attributes are emitted for compatibility.
    """
    clip = Clip(
        clip_id="c1",
        track_id="t1",
        track_kind="video",
        asset_hash="asset1",
        in_point_sec=0.0,
        out_point_sec=2.0,
        position_sec=0.0,
        effects=[Effect(effect_id="e1", effect_type="brightness", params={"value": 0.5})],
    )
    timeline = Timeline(duration_sec=2.0, tracks=[Track(track_id="t1", kind="video", clips=[clip])])
    config = EmitterConfig(enable_audio_micro_fades=False)
    xml_str = emit_timeline(timeline, config)
    root = etree.fromstring(xml_str.encode("utf-8"))

    filter_el = root.find(".//playlist/entry/filter[@id='e1']")
    assert filter_el is not None
    assert filter_el.attrib.get("mlt_service") == "brightness"
    assert filter_el.attrib.get("service") == "brightness"
    prop = filter_el.find("property[@name='level']")
    assert prop is not None, "brightness value must map to MLT 'level' property"
    assert prop.text == "0.5"


def test_emitter_color_grade_uses_avfilter_eq() -> None:
    """color_grade effect maps to MLT avfilter.eq with av.* properties."""
    clip = Clip(
        clip_id="c1",
        track_id="t1",
        track_kind="video",
        asset_hash="asset1",
        in_point_sec=0.0,
        out_point_sec=2.0,
        position_sec=0.0,
        effects=[Effect(
            effect_id="g1",
            effect_type="color_grade",
            params={"contrast": 1.06, "gamma": 1.02, "saturation": 0.98},
        )],
    )
    timeline = Timeline(duration_sec=2.0, tracks=[Track(track_id="t1", kind="video", clips=[clip])])
    config = EmitterConfig(enable_audio_micro_fades=False)
    xml_str = emit_timeline(timeline, config)
    root = etree.fromstring(xml_str.encode("utf-8"))

    filter_el = root.find(".//playlist/entry/filter[@id='g1']")
    assert filter_el is not None
    assert filter_el.attrib.get("mlt_service") == "avfilter.eq"
    props = {p.attrib["name"]: p.text for p in filter_el.findall("property")}
    assert props == {
        "av.contrast": "1.06",
        "av.gamma": "1.02",
        "av.saturation": "0.98",
    }


def test_emitter_keyframes_become_animated_property_string() -> None:
    """Effect keyframes serialize as MLT animated property strings."""
    clip = Clip(
        clip_id="c1",
        track_id="t1",
        track_kind="video",
        asset_hash="asset1",
        in_point_sec=0.0,
        out_point_sec=2.0,
        position_sec=0.0,
        effects=[Effect(
            effect_id="e1",
            effect_type="brightness",
            params={},
            keyframes={"value": [(0.0, 0.5, "linear"), (1.0, 1.0, "discrete")]},
        )],
    )
    timeline = Timeline(duration_sec=2.0, tracks=[Track(track_id="t1", kind="video", clips=[clip])])
    config = EmitterConfig(enable_audio_micro_fades=False)
    xml_str = emit_timeline(timeline, config)
    root = etree.fromstring(xml_str.encode("utf-8"))

    filter_el = root.find(".//playlist/entry/filter[@id='e1']")
    prop = filter_el.find("property[@name='level']")
    assert prop is not None
    # frame 0 linear (no marker), frame 30 discrete (!) at 30fps
    assert prop.text == "0=0.5;!30=1.0"


def test_emitter_tractor_after_playlists_and_root_producer():
    """MLT XML correctness for MULTI-track timelines (critical regression).

    melt >= 7.22 resolves <track producer=...> references at parse time and
    uses the <mlt producer=...> attribute to pick the main producer. Before
    this fix the emitter wrote the tractor BEFORE the playlists with no root
    producer attribute, so multi-track renders composited the LAST playlist
    (an audio track) -> white/static video.
    """
    clip_v = Clip(clip_id="cv", track_id="v1", track_kind="video", asset_hash="a1",
                  in_point_sec=0.0, out_point_sec=2.0, position_sec=0.0)
    clip_a = Clip(clip_id="ca", track_id="a1", track_kind="audio", asset_hash="a2",
                  in_point_sec=0.0, out_point_sec=2.0, position_sec=0.0)
    timeline = Timeline(
        duration_sec=2.0,
        tracks=[
            Track(track_id="v1", kind="video", clips=[clip_v]),
            Track(track_id="a1", kind="audio", clips=[clip_a]),
        ],
    )
    config = EmitterConfig(enable_audio_micro_fades=False)
    xml_str = emit_timeline(timeline, config, asset_paths={"a1": "/x/v.mp4", "a2": "/x/a.wav"})
    root = etree.fromstring(xml_str.encode("utf-8"))

    assert root.attrib.get("producer") == "tractor0", "mlt root must name the tractor"
    # tractor must come after ALL playlists in document order
    children = [c.tag for c in root]
    assert children.count("playlist") == 2
    assert children[-1] == "tractor", f"tractor must be last element, got {children}"
    # every track resolves to an existing playlist
    tractor = root.find("tractor")
    tracks = tractor.findall(".//track")
    playlist_ids = {p.attrib["id"] for p in root.findall("playlist")}
    for tr in tracks:
        assert tr.attrib["producer"] in playlist_ids
