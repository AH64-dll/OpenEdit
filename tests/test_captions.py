"""Caption source/history, subtitle interchange and real shared-raster timing."""
# ruff: noqa: RUF001

import subprocess
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image

from open_edit.integrations.diffusion.graphics import browser_directory
from open_edit.ir.captions import CaptionCue
from open_edit.ir.types import WordAlignment
from open_edit.kernel.captions import format_srt, from_transcript, parse_srt, store_font
from open_edit.kernel.export_service import project_timeline
from open_edit.kernel.request_history import revert_request
from open_edit.kernel.studio_service import commit_studio, get_editing_context
from open_edit.render.captions import caption_image, caption_overlays
from open_edit.render.pipe_builder import overlay_filter_chain
from open_edit.render.preview_invalidation import slice_timeline
from open_edit.serve.app import app
from open_edit.serve.routers import captions as routes
from open_edit.storage.edit_graph import EditGraphStore


def change(data, id="caption"):
    return {"kind": "caption", "object_id": id, "data": data}


def test_caption_source_history_locks_and_semantic_ai_revert(tmp_path):
    store = EditGraphStore(tmp_path / ".open_edit/edit_graph.db")
    cue = CaptionCue(text="First caption", start_sec=0.25, end_sec=1.75).model_dump(mode="json")
    commit_studio(tmp_path, expected_revision=0, changes=[change(cue)])
    commit_studio(
        tmp_path,
        expected_revision=store.graph_revision(),
        changes=[change({**cue, "text": "AI caption"})],
        author="ai",
        request_id="caption-ai",
    )
    latest = {**cue, "text": "AI caption", "style": {**cue["style"], "font_size": 72}}
    commit_studio(tmp_path, expected_revision=store.graph_revision(), changes=[change(latest)])
    revert_request(tmp_path, request_id="caption-ai", expected_revision=store.graph_revision())
    assert project_timeline(tmp_path).captions["caption"].text == "First caption"
    assert project_timeline(tmp_path).captions["caption"].style.font_size == 72
    store.history_step('undo', store.graph_revision())
    assert project_timeline(tmp_path).captions["caption"].text == "AI caption"
    store.history_step('redo', store.graph_revision())
    current = store.studio_snapshot()["objects"][0]["data"]
    commit_studio(
        tmp_path,
        expected_revision=store.graph_revision(),
        changes=[change({**current, "locked": True})],
    )
    with pytest.raises(ValueError, match="locked"):
        commit_studio(
            tmp_path,
            expected_revision=store.graph_revision(),
            changes=[change({**current, "text": "Overwrite"})],
        )
    commit_studio(
        tmp_path,
        expected_revision=store.graph_revision(),
        changes=[change({**current, "locked": False})],
    )
    assert (
        get_editing_context(tmp_path, selected_ids=["caption"])["captions"][0]["data"]["text"]
        == "First caption"
    )


def test_srt_roundtrip_keeps_unicode_multiline_and_safe_literal_text():
    source = "\ufeff1\r\n00:00:00,125 --> 00:00:01,750\r\nHello <world> {literal}\r\nمرحبا\r\n\r\n2\r\n01:00:00,000 --> 01:00:02,000\r\nLast"
    cues = [CaptionCue.model_validate(c["data"]) for c in parse_srt(source)]
    actual = [CaptionCue.model_validate(c["data"]) for c in parse_srt(format_srt(cues))]
    assert actual == cues and cues[0].text.endswith("مرحبا") and cues[1].start_sec == 3600
    with pytest.raises(ValueError):
        parse_srt("1\n00:99:00,000 --> 00:00:02,000\nBad")
    with pytest.raises(ValueError):
        parse_srt("1\n00:00:02,000 --> 00:00:01,000\nBad")


def test_transcript_caption_timing_respects_source_trim_and_clip_placement():
    words = [WordAlignment(word=str(i), t_start=i * 0.3, t_end=i * 0.3 + 0.2) for i in range(10)]
    cues = from_transcript(words, position_sec=5, in_sec=0.4, out_sec=2.5)
    assert len(cues) == 2 and cues[0]["data"]["start_sec"] == pytest.approx(5)
    assert cues[-1]["data"]["end_sec"] <= 7.1


def test_real_caption_raster_is_transparent_cached_and_uses_imported_font(tmp_path, monkeypatch):
    content = (browser_directory() / "fonts/OpenEditSans.woff2").read_bytes()
    font = store_font(tmp_path, content)
    cue = CaptionCue(
        text="Editable caption",
        start_sec=0.25,
        end_sec=0.75,
        style={"font_id": font, "font_size": 90},
    )
    image = caption_image(tmp_path, cue, 640, 360)
    with Image.open(image) as raster:
        assert raster.mode == "RGBA" and raster.size == (640, 360)
        assert raster.getpixel((0, 0))[3] == 0 and raster.getbbox()[3] > 280
        assert max(raster.getchannel("A").getextrema()) == 255
    monkeypatch.setattr(
        "open_edit.render.captions.ImageFont.truetype",
        lambda *a, **kw: pytest.fail("Cached caption rasterized again"),
    )
    assert caption_image(tmp_path, cue, 640, 360) == image


def test_actual_ffmpeg_caption_timing_and_range_slice(tmp_path):
    cue = CaptionCue(text="VISIBLE", start_sec=0.25, end_sec=0.75, style={"font_size": 100})
    overlays = caption_overlays(tmp_path, {"c": cue}, 320, 180)
    assert overlays[0].still and overlays[0].z_index == 1000000
    output = tmp_path / "captions.mp4"
    filters = overlay_filter_chain(overlays, 320, 180, first_overlay_input=1)
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=320x180:r=24:d=1",
            "-loop",
            "1",
            "-framerate",
            "24",
            "-t",
            "0.5",
            "-i",
            str(overlays[0].media_path),
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[vout]",
            "-t",
            "1",
            "-c:v",
            "libx264",
            str(output),
        ],
        check=True,
    )
    raw = subprocess.check_output(
        ["ffmpeg", "-v", "error", "-i", str(output), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    )
    frame = 320 * 180 * 3

    def bright(index):
        image = Image.frombytes("RGB", (320, 180), raw[index * frame : (index + 1) * frame])
        return sum(r > 150 and g > 150 for r, g, b in image.getdata())

    assert bright(1) == 0 and bright(12) > 30 and bright(20) == 0
    from open_edit.ir.types import Timeline

    sliced = slice_timeline(
        Timeline(captions={"c": cue}, duration_sec=1),
        render_start_frame=12,
        render_end_frame=24,
        fps_num=24,
        fps_den=1,
        plane="both",
    )
    assert sliced.captions["c"].start_sec == 0 and sliced.captions["c"].end_sec == 0.25
    assert not slice_timeline(
        sliced, render_start_frame=0, render_end_frame=12, fps_num=24, fps_den=1, plane="audio"
    ).captions


@pytest.mark.asyncio
async def test_caption_api_and_project_font_import(tmp_path, monkeypatch):
    async def require(_):
        return SimpleNamespace(path=str(tmp_path))

    monkeypatch.setattr(routes, "_require_project", require)
    store = EditGraphStore(tmp_path / ".open_edit/edit_graph.db")
    cue = CaptionCue(text="Caption API", start_sec=0, end_sec=1).model_dump(mode="json")
    commit_studio(tmp_path, expected_revision=0, changes=[change(cue)])
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        assert (
            await client.get("/api/projects/p/captions/caption/image?width=320&height=180")
        ).headers["content-type"] == "image/png"
        assert "Caption API" in (await client.get("/api/projects/p/captions.srt")).text
        response = await client.post(
            "/api/projects/p/fonts",
            data={"expected_revision": store.graph_revision(), "label": "My local font"},
            files={
                "file": (
                    "font.woff2",
                    (browser_directory() / "fonts/OpenEditSans.woff2").read_bytes(),
                )
            },
        )
        assert response.status_code == 201, response.text
        assert get_editing_context(tmp_path)["fonts"][0]["data"]["label"] == "My local font"
