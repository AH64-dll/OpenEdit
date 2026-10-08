"""Pinned synthetic color/tone fixtures check source, frame and audio time."""
from __future__ import annotations

import array
import subprocess
from itertools import pairwise

import pytest
from PIL import Image

from open_edit.integrations.diffusion.timing import bake_timing
from open_edit.storage.assets import AssetStore
from open_edit.storage.edit_graph import EditGraphStore


@pytest.fixture(params=[24, '30000/1001'])
def timing_source(tmp_path, request):
    root = tmp_path / 'timing-project'
    store = EditGraphStore(root / '.open_edit/edit_graph.db')
    output = tmp_path / 'golden-source.mkv'
    subprocess.run(['ffmpeg', '-y', '-v', 'error',
                    '-f', 'lavfi', '-i', f'color=red:s=64x32:r={request.param}:d=1',
                    '-f', 'lavfi', '-i', f'color=blue:s=64x32:r={request.param}:d=1',
                    '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=1',
                    '-f', 'lavfi', '-i', 'sine=frequency=880:sample_rate=48000:duration=1',
                    '-filter_complex', '[0:v][1:v]concat=n=2:v=1:a=0[v];[2:a][3:a]concat=n=2:v=0:a=1[a]',
                    '-map', '[v]', '-map', '[a]', '-c:v', 'ffv1', '-c:a', 'pcm_s16le', str(output)], check=True)
    asset = AssetStore(root / '.open_edit/assets').ingest(str(output), transcribe=False)
    return root, store, asset


def pixel(path, time):
    data = subprocess.check_output(['ffmpeg', '-v', 'error', '-ss', str(time), '-i', str(path),
                                    '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'])
    return tuple(data[:3])


def frequency(path, start, duration=0.1):
    data = subprocess.check_output(['ffmpeg', '-v', 'error', '-ss', str(start), '-i', str(path), '-t', str(duration),
                                    '-vn', '-ac', '1', '-ar', '48000', '-f', 's16le', '-'])
    samples = array.array('h', data)
    assert len(samples) >= duration * 48000 - 2
    crossings = sum(a <= 0 < b for a, b in pairwise(samples))
    return crossings / duration


def cas(root, hash_):
    return root / '.open_edit/assets' / hash_[:2] / hash_


def test_source_in_constant_rate_pitch_and_cache(timing_source):
    root, store, asset = timing_source
    result = bake_timing(root, asset_hash=asset.asset_hash, source_in=1.1, source_out=1.9, playback_rate=2, fps=30)
    assert result['duration_sec'] == pytest.approx(0.4)
    path = cas(root, result['asset_hash'])
    r, _g, b = pixel(path, 0.1)
    assert b > 200 and r < 20
    assert frequency(path, 0.1) == pytest.approx(880, abs=20)
    again = bake_timing(root, asset_hash=asset.asset_hash, source_in=1.1, source_out=1.9, playback_rate=2, fps=30)
    assert again['cache_hit']
    assert again['asset_hash'] == result['asset_hash']
    assert store.graph_revision() == 0


def test_piecewise_speed_ramp_source_time_and_audio(timing_source):
    root, _, asset = timing_source
    result = bake_timing(root, asset_hash=asset.asset_hash,
                         segments=[{'source_in': 0, 'source_out': 1, 'rate': 1}, {'source_in': 1, 'source_out': 2, 'rate': 2}], fps=30)
    assert result['duration_sec'] == 1.5
    path = cas(root, result['asset_hash'])
    red, blue = pixel(path, 0.4), pixel(path, 1.3)
    assert red[0] > 200 and red[2] < 20
    assert blue[2] > 200 and blue[0] < 20
    assert frequency(path, 0.4) == pytest.approx(440, abs=20)
    assert frequency(path, 1.2) == pytest.approx(880, abs=20)


def test_still_offsets_and_speed(tmp_path):
    root = tmp_path / 'still-project'
    EditGraphStore(root / '.open_edit/edit_graph.db')
    original = tmp_path / 'still.png'
    Image.new('RGBA', (64, 32), (0, 255, 0, 128)).save(original)
    asset = AssetStore(root / '.open_edit/assets').ingest(str(original), transcribe=False)
    result = bake_timing(root, asset_hash=asset.asset_hash, source_in=2, source_out=6, playback_rate=2, fps=25)
    assert result['duration_sec'] == 2
    assert not result['qc_report']['audio']
    assert pixel(cas(root, result['asset_hash']), 1.5)[1] > 240


def test_audio_only_slow_motion_and_invalid_input(tmp_path):
    root = tmp_path / 'audio-project'
    EditGraphStore(root / '.open_edit/edit_graph.db')
    original = tmp_path / 'tone.wav'
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1:sample_rate=48000', str(original)], check=True)
    asset = AssetStore(root / '.open_edit/assets').ingest(str(original), transcribe=False)
    result = bake_timing(root, asset_hash=asset.asset_hash, source_in=0.1, source_out=0.9, playback_rate=0.25)
    assert result['duration_sec'] == pytest.approx(3.2)
    assert frequency(cas(root, result['asset_hash']), 1) == pytest.approx(440, abs=20)
    for rate in [0, True, float('nan'), 9]:
        with pytest.raises(ValueError):
            bake_timing(root, asset_hash=asset.asset_hash, source_out=0.9, playback_rate=rate)


def test_jsx_rate_commit_noop_and_other_editor_trim(timing_source):
    from open_edit.integrations.diffusion.authoring import apply_authoring_edit, get_authoring_view
    from open_edit.integrations.diffusion.compiler import worker_ready
    from open_edit.ir.derive import derive_timeline
    from open_edit.ir.types import AddClipOp, Project, TrimClipOp

    if not worker_ready():
        pytest.skip('Optional compiler worker not installed')
    root, store, asset = timing_source
    store.append(AddClipOp(author='ai', clip_id='hero', track_id='main', asset_hash=asset.asset_hash, position_sec=0, out_point_sec=2))
    result = apply_authoring_edit(root, expected_revision=store.graph_revision(), edits=[{
        'kind': 'set', 'source': 'index.tsx:c-hero', 'props': {'sourceIn': 1.1, 'sourceOut': 1.9, 'playbackRate': 2},
    }])
    view = get_authoring_view(root, include_source=True)
    assert view['graph_revision'] == result['graph_revision']
    assert view['elements'][0]['playbackRate'] == 2
    assert view['elements'][0]['sourceIn'] == pytest.approx(1.1)
    timeline = derive_timeline(Project(project_id=store.project_id, name='p', workdir=root, edit_graph=store.load_all()))
    clip = timeline.tracks[0].clips[0]
    assert clip.asset_hash != asset.asset_hash
    assert clip.out_point_sec == pytest.approx(0.4)
    noop = apply_authoring_edit(root, expected_revision=store.graph_revision(), source=view['source'])
    assert noop['ops_appended'] == 0
    store.append(TrimClipOp(author='user', clip_id='hero', new_in_point_sec=0.1, new_out_point_sec=0.3))
    refreshed = get_authoring_view(root, include_source=True)
    assert refreshed['elements'][0]['sourceIn'] == pytest.approx(1.3)
    assert refreshed['elements'][0]['sourceOut'] == pytest.approx(1.7)
    assert refreshed['elements'][0]['playbackRate'] == 2
    again = apply_authoring_edit(root, expected_revision=store.graph_revision(), source=refreshed['source'])
    assert again['ops_appended'] == 0
