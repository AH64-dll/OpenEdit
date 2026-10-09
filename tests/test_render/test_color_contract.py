"""Decoded palette colors agree across raw pipes, overlays, previews and exports."""
import json
import shutil
import subprocess
import wave
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from open_edit.render.encoder import select_encoder
from open_edit.render.pipe_builder import OverlayClip, build_pipe_commands
from open_edit.render.preview_pipe import build_preview_pipe_commands
from open_edit.render.profiles import preview_chunk_profile, profile_with_quality

COLORS = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (39, 121, 195),
          (255, 204, 85), (255, 0, 255), (128, 128, 128), (255, 255, 255)]


def _palette(path: Path, width=128, height=64):
    image = Image.new('RGBA', (width, height))
    draw = ImageDraw.Draw(image)
    for index, color in enumerate(COLORS):
        x = index % 4 * width // 4
        y = index // 4 * height // 2
        draw.rectangle((x, y, x + width // 4 - 1, y + height // 2 - 1), fill=(*color, 255))
    image.save(path)


def _run(command, **kwargs):
    result = subprocess.run(command, capture_output=True, timeout=40, **kwargs)
    assert result.returncode == 0, result.stderr.decode(errors='replace')[-4000:]
    return result.stdout


def _samples(path: Path):
    stream = json.loads(_run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                             '-show_entries', 'stream=width,height,color_space,color_range,color_primaries,color_transfer',
                             '-of', 'json', str(path)]))['streams'][0]
    width, height = stream['width'], stream['height']
    raw = _run(['ffmpeg', '-v', 'error', '-i', str(path), '-frames:v', '1',
                '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'])
    colors = []
    for index in range(len(COLORS)):
        x = (2 * (index % 4) + 1) * width // 8
        y = (2 * (index // 4) + 1) * height // 4
        offset = (y * width + x) * 3
        colors.append(list(raw[offset:offset + 3]))
    assert stream['color_space'] == stream['color_primaries'] == stream['color_transfer'] == 'bt709'
    assert stream['color_range'] == 'tv'
    assert max(abs(actual - expected) for color, original in zip(colors, COLORS, strict=True)
               for actual, expected in zip(color, original, strict=True)) <= 8, colors
    return colors


@pytest.mark.parametrize('pipeline', ['whole', 'chunk'])
@pytest.mark.parametrize('overlay', [False, True])
def test_actual_ffmpeg_raw_pipe_and_rgb_overlay_preserve_palette(tmp_path, pipeline, overlay):
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        pytest.skip('FFmpeg required')
    png = tmp_path / 'palette.png'
    _palette(png)
    frame = _run(['ffmpeg', '-v', 'error', '-i', str(png), '-frames:v', '1',
                  '-vf', 'scale=out_color_matrix=bt709:out_range=tv,format=nv12',
                  '-f', 'rawvideo', '-'])
    profile = profile_with_quality(None, 'proxy', quality='high', overrides={'width': 128, 'height': 64})
    encoder = select_encoder('cpu', tier='high')
    output = tmp_path / 'output.mp4'
    overlays = [OverlayClip(0, .4, png, still=True)] if overlay else []
    if pipeline == 'whole':
        commands = build_pipe_commands('melt', tmp_path / 'unused.mlt', output, profile, encoder, overlays)
        with wave.open(str(commands.audio_wav), 'wb') as audio:
            audio.setnchannels(2)
            audio.setsampwidth(2)
            audio.setframerate(48000)
            audio.writeframes(b'\0' * 19200 * 4)
        command = commands.ffmpeg_cmd
    else:
        commands = build_preview_pipe_commands(
            melt_bin='melt', xml_path=tmp_path / 'unused.mlt', video_output=output,
            audio_output=None, playback_output=output, profile=profile, encoder=encoder,
            overlays=overlays, crop_head_frames=0, crop_tail_frames=0, core_frames=12, media='video')
        command = commands.video_cmd[commands.video_cmd.index('|') + 1:]
    _run(command, input=frame * 12)
    _samples(output)


@pytest.mark.browser
def test_actual_mlt_checked_preview_matches_immutable_final_export(tmp_path, monkeypatch):
    if not all(shutil.which(binary) for binary in ('melt', 'ffmpeg', 'ffprobe')):
        pytest.skip('MLT and FFmpeg required')
    from open_edit.ir.derive import derive_timeline
    from open_edit.ir.types import AddClipOp, Project
    from open_edit.kernel.export_service import ExportSettings, capture_export, execute_export
    from open_edit.render.emitter import EmitterConfig, emit_timeline
    from open_edit.render.orchestrator import render_project
    from open_edit.render.preview_chunks import run_preview_pipe
    from open_edit.storage.assets import AssetStore
    from open_edit.storage.edit_graph import EditGraphStore

    monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
    monkeypatch.setenv('SDL_VIDEODRIVER', 'dummy')
    png, source = tmp_path / 'palette.png', tmp_path / 'palette.mov'
    _palette(png, 320, 180)
    _run(['ffmpeg', '-v', 'error', '-loop', '1', '-framerate', '30', '-i', str(png),
          '-t', '0.4', '-c:v', 'qtrle', '-pix_fmt', 'argb', str(source)])
    assets = AssetStore(tmp_path / '.open_edit/assets')
    asset = assets.ingest(str(source), transcribe=False)
    store = EditGraphStore(tmp_path / '.open_edit/edit_graph.db')
    store.append(AddClipOp(author='user', clip_id='palette', asset_hash=asset.asset_hash,
                           track_id='video', position_sec=0, out_point_sec=.4))
    revision = store.graph_revision()
    proxy = render_project('palette', tmp_path, tmp_path / 'proxy', mode='proxy',
                           encoder_backend='cpu', overrides={'scale': '320x180'}, force=True)
    assert proxy.ok, proxy.error
    previews = {'whole': _samples(Path(proxy.output_path))}

    profile = preview_chunk_profile()
    xml = tmp_path / 'chunk.mlt'
    xml.write_text(emit_timeline(derive_timeline(Project(name='palette', edit_graph=store.load_all())), EmitterConfig(profile=profile.model_dump()),
                                asset_paths={asset.asset_hash: str(assets.path(asset.asset_hash))}))
    chunk = tmp_path / 'chunk.mp4'
    run_preview_pipe(build_preview_pipe_commands(
        melt_bin=shutil.which('melt'), xml_path=xml, video_output=chunk,
        audio_output=None, playback_output=chunk, profile=profile,
        encoder=select_encoder('cpu', tier='fast'), overlays=[], crop_head_frames=0,
        crop_tail_frames=0, core_frames=12, media='video'))
    previews['chunk'] = _samples(chunk)

    settings = ExportSettings(filename='Palette parity', folder=str(tmp_path / 'Local Desktop'),
                              width=320, height=180, fps_num=30, encoder='cpu', audio=False)
    final = execute_export(tmp_path, capture_export(tmp_path, revision, settings))
    assert final['export_verification']['passed'] and final['export_verification']['full_decode']
    exported = _samples(Path(final['output_path']))
    for preview in previews.values():
        assert max(abs(a - b) for color, other in zip(preview, exported, strict=True)
                   for a, b in zip(color, other, strict=True)) <= 8, (preview, exported)
    artifacts = Path('tests/browser/artifacts')
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / 'studio-color-parity.json').write_text(json.dumps(
        {'expected': COLORS, 'previews': previews, 'export': exported,
         'verification': final['export_verification']}, indent=2))
    assert store.graph_revision() == revision
