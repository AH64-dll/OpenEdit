"""Real source timestamps, bounded transcript retrieval, cache reuse and MCP images."""
import json
import subprocess
import sys

import pytest
from PIL import Image

from open_edit.ir.types import WordAlignment
from open_edit.kernel.media_context import inspect_media
from open_edit.kernel.pillar_tools import dispatch_query
from open_edit.storage.assets import AssetStore
from open_edit.storage.edit_graph import EditGraphStore


@pytest.fixture
def media(tmp_path, monkeypatch):
    monkeypatch.setenv('OPEN_EDIT_SOURCE_PROXY_AUTO', '0')
    source = tmp_path / 'red-blue.mp4'
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi', '-i',
                    'color=red:s=320x180:r=30:d=1', '-f', 'lavfi', '-i',
                    'color=blue:s=320x180:r=30:d=1', '-filter_complex',
                    '[0:v][1:v]concat=n=2:v=1:a=0', '-c:v', 'libx264',
                    '-pix_fmt', 'yuv420p', str(source)], check=True)
    store = AssetStore(tmp_path / '.open_edit/assets')
    asset = store.ingest(str(source), transcribe=False)
    store.update_alignment(asset.asset_hash, [WordAlignment(word=f'word{i}', t_start=i / 10,
                                                          t_end=(i + 1) / 10) for i in range(20)])
    EditGraphStore(tmp_path / '.open_edit/edit_graph.db')
    return tmp_path, asset.asset_hash


def test_samples_have_exact_source_times_and_survive_reopen(media, monkeypatch):
    root, hash_ = media
    result = inspect_media(root, asset_hash=hash_, frames=2)
    assert result['frames'][0]['source_sec'] == 0
    assert result['frames'][1]['source_sec'] == pytest.approx(2 - 1 / 30, abs=1e-6)
    with Image.open(result['image_path']) as image:
        assert image.getpixel((160, 90))[0] > 200
        assert image.getpixel((480, 90))[2] > 200
    monkeypatch.setattr('open_edit.kernel.media_context._run', lambda *a, **kw: pytest.fail('Decoded cached source'))
    reopened = inspect_media(root, asset_hash=hash_, frames=2)
    assert reopened['cache_hit'] and reopened['image_path'] == result['image_path']


def test_range_transcript_pages_without_decoding(media, monkeypatch):
    root, hash_ = media
    monkeypatch.setattr('open_edit.kernel.media_context._run', lambda *a, **kw: pytest.fail('Transcript decoded video'))
    first = inspect_media(root, asset_hash=hash_, frames=0, start_sec=1, end_sec=2, transcript_limit=3)
    assert first['frames'] == [] and 'image_path' not in first
    assert first['transcript']['range_words'] == 10
    assert first['transcript']['returned_words'] == 3 and first['transcript']['next_offset'] == 3
    assert 'word10' in first['transcript']['text'] and 'word0 ' not in first['transcript']['text']
    second = inspect_media(root, asset_hash=hash_, frames=0, start_sec=1, end_sec=2,
                           transcript_limit=3, word_offset=3)
    assert 'word13' in second['transcript']['text'] and 'word10' not in second['transcript']['text']


@pytest.mark.parametrize('params', [{'frames': 13}, {'frames': True}, {'start_sec': float('nan')},
                                   {'end_sec': 3}, {'start_sec': -1}, {'transcript_limit': 501}])
def test_bad_retrieval_never_decodes(media, monkeypatch, params):
    root, hash_ = media
    monkeypatch.setattr('open_edit.kernel.media_context._run', lambda *a, **kw: pytest.fail('Invalid request decoded video'))
    result = dispatch_query('inspect_media', {'asset_hash': hash_, **params}, root)
    assert result['status'] == 'error'


@pytest.mark.asyncio
async def test_real_stdio_mcp_returns_visual_content(media):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    root, hash_ = media
    params = StdioServerParameters(command=sys.executable,
                                  args=['-m', 'open_edit.mcp.server', '--project', str(root)])
    async with stdio_client(params) as (reader, writer), ClientSession(reader, writer) as session:
        await session.initialize()
        result = await session.call_tool('query_project', {'query': 'inspect_media',
                                        'params': {'asset_hash': hash_, 'frames': 2}})
        assert not result.isError
        assert [item.type for item in result.content] == ['text', 'image']
        assert result.content[1].mimeType == 'image/jpeg'
        assert json.loads(result.content[0].text)['frames'][1]['source_sec'] > 1
        help_ = await session.call_tool('query_project', {'query': 'describe', 'params': {'name': 'trim_clip'}})
        assert not help_.isError and 'clip_id' in help_.content[0].text


def test_registry_does_not_load_optional_engines():
    command = "from open_edit.agent.tools import TOOL_TABLE; import sys; assert len(TOOL_TABLE) > 20; assert 'open_edit.integrations.diffusion.graphics' not in sys.modules; assert 'open_edit.agent.tools.pyagent_search_assets' not in sys.modules"
    subprocess.run([sys.executable, '-c', command], check=True)


@pytest.mark.asyncio
async def test_real_trim_reuses_unaffected_preview_chunks(media, monkeypatch):
    import shutil
    if not shutil.which('melt'):
        pytest.skip('MLT required for real preview cache validation')
    from open_edit.ir.hash import compute_edit_graph_hash
    from open_edit.ir.types import AddClipOp, TrimClipOp
    from open_edit.kernel.render_jobs import RenderJobService
    from open_edit.kernel.studio_service import commit_studio

    monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
    monkeypatch.setenv('SDL_VIDEODRIVER', 'dummy')
    root, hash_ = media
    store = EditGraphStore(root / '.open_edit/edit_graph.db')
    commit_studio(root, expected_revision=0, changes=[], label='Arrange clips', ops=[
        AddClipOp(author='user', clip_id=str(i), asset_hash=hash_, track_id='v1',
                  position_sec=i * 2, out_point_sec=2).model_dump(mode='json') for i in range(3)])
    service = RenderJobService(timeout_s=120)
    try:
        async def render(ranges=None):
            job = service.enqueue('test', root, 'preview-chunks', expected_revision=store.graph_revision(),
                                  params={'media': 'both', 'encoder': 'cpu', 'ranges': ranges or []})
            result = await service.wait(root, job.job_id)
            assert result.status == 'succeeded', result.error
            return result.result

        local = await render([{'start_sec': 0, 'end_sec': 1}])
        assert 0 < local['green_chunks'] < local['diagnostics']['counts']['total_chunks']
        filled = await render()
        assert filled['red_chunks'] == 0 and filled['yellow_chunks'] == 0
        assert filled['diagnostics']['counts']['processed_chunks'] > 0
        old_hash = compute_edit_graph_hash(store.load_all())
        assert store.load_timeline_snapshot(old_hash)
        commit_studio(root, expected_revision=store.graph_revision(), changes=[], label='Trim', ops=[
            TrimClipOp(author='user', clip_id='0', new_in_point_sec=.25,
                       new_out_point_sec=2).model_dump(mode='json')])
        assert store.load_timeline_snapshot(old_hash)
        new_hash = compute_edit_graph_hash(store.load_all())
        assert new_hash != old_hash and store.load_timeline_snapshot(new_hash) is None
        edited = await render()
        counts = edited['diagnostics']['counts']
        assert 0 < counts['processed_chunks'] < counts['total_chunks'], counts
        assert edited['diagnostics']['cache']['hits'] > 0
    finally:
        await service.shutdown()
