"""Real bounded FFmpeg source caches survive reopen without another decode."""
import subprocess
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image

from open_edit.render.asset_visuals import asset_visuals
from open_edit.serve.app import app
from open_edit.serve.routers import assets as routes
from open_edit.storage.assets import AssetStore


def ingest(root, kind='audio'):
    path = root / ('tone.wav' if kind=='audio' else 'video.mp4')
    args = ['-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=0.5',
            '-af','adelay=500|500','-c:a','pcm_s16le'] if kind=='audio' else [
            '-f','lavfi','-i','color=c=red:s=320x180:r=30:d=1','-c:v','libx264','-pix_fmt','yuv420p']
    subprocess.run(['ffmpeg','-v','error','-y',*args,str(path)],check=True)
    return AssetStore(root/'.open_edit/assets').ingest(str(path),transcribe=False)


def test_waveform_is_bounded_timed_and_persistent(tmp_path,monkeypatch):
    asset = ingest(tmp_path)
    data = asset_visuals(tmp_path,asset.asset_hash)
    peaks = data['waveform']['peaks']
    assert 1 < len(peaks) <= 2050 and all(0<=v<=1 for v in peaks)
    assert max(peaks[:len(peaks)//3]) == 0 and max(peaks[-len(peaks)//3:]) > .05
    assert len(peaks)*data['waveform']['step_sec'] == pytest.approx(asset.duration_sec,abs=.01)
    assert not data['thumbnails']
    def forbidden(*a,**kw):
        raise AssertionError('Cached media was decoded again')
    monkeypatch.setattr('open_edit.render.asset_visuals._run',forbidden)
    assert asset_visuals(tmp_path,asset.asset_hash) == data


def test_filmstrip_samples_exactly_six_frames(tmp_path):
    asset = ingest(tmp_path,'video')
    data = asset_visuals(tmp_path,asset.asset_hash)
    assert len(data['thumbnails']) == 6 and not data['waveform']['peaks']
    assert data['thumbnails'][0]['time_sec'] == 0
    assert data['thumbnails'][-1]['time_sec'] < 1
    for thumb in data['thumbnails']:
        with Image.open(tmp_path/'.open_edit/cache/visuals'/asset.asset_hash/thumb['file']) as image:
            assert image.size == (320,180) and image.getpixel((160,90))[0] > 200


@pytest.mark.parametrize('hash',['../outside','x'*64,'a'*63,''])
def test_visual_cache_rejects_non_cas_paths(tmp_path,hash):
    with pytest.raises(ValueError):
        asset_visuals(tmp_path,hash)


@pytest.mark.asyncio
async def test_visual_routes_and_safe_thumbnail_serving(tmp_path,monkeypatch):
    asset = ingest(tmp_path,'video')
    async def require(_):
        return SimpleNamespace(path=str(tmp_path))
    monkeypatch.setattr(routes,'_require_project',require)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://localhost') as client:
        root=f'/api/projects/p/assets/{asset.asset_hash}/visuals'
        response=await client.get(root)
        assert response.status_code==200
        thumb=await client.get(response.json()['thumbnails'][2]['url'])
        assert thumb.status_code==200 and thumb.headers['content-type']=='image/jpeg'
        assert (await client.get(root+'/6')).status_code==404
        assert (await client.get('/api/projects/p/assets/invalid/visuals')).status_code==400
        assert (await client.get('/api/projects/p/assets/'+'b'*64+'/visuals')).status_code==404
