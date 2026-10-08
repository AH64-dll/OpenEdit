"""Real grammar/encoding tests, including transactional publication and restart."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from open_edit.integrations.diffusion.graphics import (
    DEFAULT_SOURCE,
    _quality_check,
    commit_graphics,
    graphics_ready,
    inspect_source,
    validate_params,
)
from open_edit.storage.edit_graph import EditGraphStore


@pytest.fixture
def graphics_project(tmp_path):
    root = tmp_path / 'graphics-project'
    (root / '.open_edit').mkdir(parents=True)
    store = EditGraphStore(root / '.open_edit/edit_graph.db')
    return root, store


@pytest.fixture
def graphics_worker():
    if not graphics_ready():
        pytest.skip('Optional pinned graphics worker is not installed')


def test_graphics_bounds():
    result = validate_params({'source': DEFAULT_SOURCE, 'duration_sec': 1.01, 'fps': 30})
    assert result['duration_sec'] == pytest.approx(31 / 30)
    for values in ({'source': DEFAULT_SOURCE, 'fps': True}, {'source': DEFAULT_SOURCE, 'duration_sec': float('nan')},
                   {'source': DEFAULT_SOURCE, 'fps': 60, 'duration_sec': 60}, {'source': DEFAULT_SOURCE, 'unexpected': 1}):
        with pytest.raises(ValueError):
            validate_params(values)


def test_actual_graphics_compiler_rejects_executable_sources(graphics_worker):
    document = inspect_source(DEFAULT_SOURCE)
    assert document['scene']['width'] == 960
    assert document['elements'][-1]['tag'] == 'text'
    for bad in (DEFAULT_SOURCE.replace('x={60}', 'x={globalThis.process.exit()}'),
                'import "https://example.com";\n' + DEFAULT_SOURCE,
                DEFAULT_SOURCE.replace('id="title"', 'id="panel"'),
                DEFAULT_SOURCE.replace('width={960}', 'width={99999}'),
                DEFAULT_SOURCE.replace('<rect id="panel"', '<html id="panel"'),
                DEFAULT_SOURCE.replace('fontSize={48}', 'ref={() => fetch("https://example.com")}')):
        with pytest.raises(ValueError):
            inspect_source(bad)


def test_rgba_encoding_quality_gate(tmp_path):
    if not shutil.which('ffmpeg'):
        pytest.skip('FFmpeg required')
    frame = tmp_path / 'frame.png'
    Image.new('RGBA', (64, 32), (255, 0, 0, 120)).save(frame)
    output = tmp_path / 'alpha.mov'
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-loop', '1', '-i', str(frame), '-t', '0.5',
                    '-r', '30', '-c:v', 'qtrle', '-pix_fmt', 'argb', str(output)], check=True)
    assert _quality_check(output, width=64, height=32, duration=0.5, fps=30)['passed']
    with pytest.raises(ValueError, match='QC failed'):
        _quality_check(output, width=66, height=32, duration=0.5, fps=30)


def test_failed_or_absent_preview_never_commits(graphics_project):
    root, store = graphics_project
    revision = store.graph_revision()
    with pytest.raises(ValueError, match='succeeded graphics job'):
        commit_graphics(root, job_id='missing', expected_revision=revision)
    assert store.graph_revision() == revision


GOLDEN_SOURCE = '''export default function Golden() {
 return <stage id="root"><scene id="scene" width={320} height={180} active>
  <rect id="moving" x={10} y={10} width={40} height={30} fill="#ff0000" end={1}>
   <keyframeTrack id="motion" property="x"><keyframe id="k0" time={0} value={10}/><keyframe id="k1" time={1} value={110}/></keyframeTrack>
  </rect>
  <rect id="behind" x={200} y={10} width={40} height={30} fill="#0000ff" end={1}/>
  <rect id="front" x={220} y={10} width={40} height={30} fill="#00ff00" end={1}/>
  <group id="masked" x={200} y={60} end={1}>
   <rect id="matte" width={30} height={40} clipPath />
   <rect id="panel" width={60} height={40} fill="#ff00ff" />
  </group>
  <text id="title" x={10} y={110} width={280} height={40} fontFamily="OpenEdit Sans" fontSize={24} color="#ffffff" end={1}>OpenEdit</text>
 </scene></stage>;
}'''


@pytest.mark.browser
@pytest.mark.asyncio
async def test_browser_graphics_golden_cache_commit_and_failure(graphics_project, graphics_worker, monkeypatch):
    from open_edit.kernel.render_jobs import RenderJobService, public_job
    from open_edit.storage.edit_graph import GraphRevisionConflict

    root, store = graphics_project
    service = RenderJobService(timeout_s=180)
    params = {'source': GOLDEN_SOURCE, 'duration_sec': 1, 'fps': 30}
    revision = store.graph_revision()
    job = service.enqueue('graphics-project', root, 'graphics', expected_revision=revision, params=params)
    done = await service.wait(root, job.job_id)
    assert done.status == 'succeeded', done.error
    assert done.result['qc_report']['passed']
    assert 'source' not in public_job(done, include_details=False)['result']
    assert store.graph_revision() == revision
    output = Path(done.output_path)
    def decoded(frame):
        data = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(output), '-vf', f'select=eq(n\\,{frame})',
                                        '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgba', '-'])
        return Image.frombytes('RGBA', (320, 180), data)
    start, middle = decoded(0), decoded(15)
    artifacts = Path('tests/browser/artifacts')
    artifacts.mkdir(exist_ok=True)
    start.save(artifacts / 'graphics-golden-start.png')
    middle.save(artifacts / 'graphics-golden-middle.png')
    assert start.getpixel((20, 20)) == (255, 0, 0, 255)
    assert middle.getpixel((20, 20))[3] == 0
    assert middle.getpixel((70, 20)) == (255, 0, 0, 255)
    assert start.getpixel((230, 20)) == (0, 255, 0, 255)
    assert start.getpixel((210, 70)) == (255, 0, 255, 255)
    assert start.getpixel((245, 70))[3] == 0
    assert start.getpixel((310, 170))[3] == 0
    assert sum(1 for r, g, b, a in start.crop((10, 110, 290, 150)).getdata() if r > 200 and g > 200 and b > 200 and a) > 100
    # A fresh service can use the durable job and the verified cache.
    again = service.enqueue('graphics-project', root, 'graphics', expected_revision=revision, params=params)
    cached = await service.wait(root, again.job_id)
    assert cached.status == 'succeeded', cached.error
    assert cached.result['cache_hit']
    committed = commit_graphics(root, job_id=job.job_id, expected_revision=revision)
    assert committed['asset_hash'] == done.result['asset_hash']
    with pytest.raises(GraphRevisionConflict):
        commit_graphics(root, job_id=job.job_id, expected_revision=revision)
    last_good = (root / '.open_edit/graphics/last-good.json').read_text()
    bad = service.enqueue('graphics-project', root, 'graphics', expected_revision=store.graph_revision(),
                          params={**params, 'source': 'export default function Nope(){throw Error("bad");}'})
    failed = await service.wait(root, bad.job_id)
    assert failed.status == 'failed'
    assert (root / '.open_edit/graphics/last-good.json').read_text() == last_good
    assert len(store.load_all()) == 1
    changed = service.enqueue('graphics-project', root, 'graphics', expected_revision=store.graph_revision(),
                              params={**params, 'source': GOLDEN_SOURCE.replace('#ff0000', '#ffff00')})
    updated = await service.wait(root, changed.job_id)
    assert updated.status == 'succeeded', updated.error
    assert not updated.result['cache_hit']
    assert updated.result['content_key'] != done.result['content_key']
    # This acceptance path provisions MLT on Linux; other OS jobs cover workers.
    if os.name == 'posix' and shutil.which('melt'):
        from open_edit.render.orchestrator import render_project

        monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
        monkeypatch.setenv('SDL_VIDEODRIVER', 'dummy')
        exported = render_project(project_id='graphics-project', project_dir=root,
                                  workdir=root / 'renders', mode='proxy',
                                  overrides={'scale': '320x180'}, force=True)
        assert exported.ok, exported.error
        raw = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', exported.output_path,
                                       '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'])
        frame = Image.frombytes('RGB', (320, 180), raw)
        frame.save(artifacts / 'graphics-timeline-export.png')
        red, green, blue = frame.getpixel((20, 20))
        # This scaled H.264 proxy is lossy; exact RGBA is checked above.
        assert red > 200 and green < 25 and blue < 25
        assert max(frame.getpixel((310, 170))) < 25
    await service.shutdown()


@pytest.mark.browser
@pytest.mark.asyncio
async def test_browser_cas_image_and_sequence_transition(graphics_project, graphics_worker):
    from open_edit.kernel.render_jobs import RenderJobService
    from open_edit.storage.assets import AssetStore

    root, store = graphics_project
    image = root / 'reference.png'
    Image.new('RGBA', (40, 40), (255, 128, 0, 255)).save(image)
    asset = AssetStore(root / '.open_edit/assets').ingest(str(image), transcribe=False)
    source = GOLDEN_SOURCE.replace('</scene>', f'''<image id="reference" src="asset://{asset.asset_hash}" x={{270}} y={{50}} width={{40}} height={{40}} end={{2}} />
     <sequence id="cuts"><rect id="outgoing" x={{110}} y={{60}} width={{40}} height={{40}} fill="#0000ff" end={{1}} transition={{{{type: "dissolve", duration: 0.4}}}} />
     <rect id="incoming" x={{110}} y={{60}} width={{40}} height={{40}} fill="#ff0000" start={{1}} end={{2}} /></sequence></scene>''')
    service = RenderJobService(timeout_s=180)
    params = {'source': source, 'duration_sec': 2, 'fps': 20}
    job = service.enqueue('graphics-project', root, 'graphics', expected_revision=store.graph_revision(), params=params)
    done = await service.wait(root, job.job_id)
    assert done.status == 'succeeded', done.error
    def frame(index):
        raw = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', done.output_path, '-vf', f'select=eq(n\\,{index})',
                                       '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgba', '-'])
        return Image.frombytes('RGBA', (320, 180), raw)
    start, cut, end = frame(0), frame(20), frame(30)
    artifacts = Path('tests/browser/artifacts')
    artifacts.mkdir(exist_ok=True)
    cut.save(artifacts / 'graphics-transition.png')
    assert start.getpixel((280, 70)) == (255, 128, 0, 255)
    assert start.getpixel((130, 80)) == (0, 0, 255, 255)
    red, green, blue, alpha = cut.getpixel((130, 80))
    assert 80 <= red <= 180 and green == 0 and 80 <= blue <= 180 and alpha > 200
    assert end.getpixel((130, 80)) == (255, 0, 0, 255)
    assert store.graph_revision() == 0
    # A modified CAS file invalidates even a previously successful cached render.
    (root / '.open_edit/assets' / asset.asset_hash[:2] / asset.asset_hash).write_bytes(b'corrupt')
    failed = service.enqueue('graphics-project', root, 'graphics', expected_revision=0, params=params)
    rejected = await service.wait(root, failed.job_id)
    assert rejected.status == 'failed'
    assert 'hash mismatch' in rejected.error
    assert service.latest_succeeded(root, 'graphics').job_id == done.job_id
    await service.shutdown()


@pytest.mark.browser
@pytest.mark.asyncio
async def test_cancel_reaps_chromium_and_restart(graphics_project, graphics_worker):
    import asyncio

    from open_edit.kernel.render_jobs import RenderJobService

    root, store = graphics_project
    service = RenderJobService(timeout_s=180)
    job = service.enqueue('graphics-project', root, 'graphics', expected_revision=store.graph_revision(),
                          params={'source': GOLDEN_SOURCE, 'duration_sec': 60, 'fps': 30})
    pid = None
    for _ in range(600):
        records = list((root / '.open_edit/graphics').glob('capture-*/processes.json'))
        if records:
            pid = json.loads(records[0].read_text())['chromium']
            break
        current = service.get(root, job.job_id)
        assert current.status not in ('succeeded', 'failed'), current.error
        await asyncio.sleep(0.05)
    assert pid is not None, 'Chromium never started'
    await service.cancel(root, job.job_id)
    cancelled = await service.wait(root, job.job_id)
    assert cancelled.status == 'cancelled'
    for _ in range(100):
        if os.name == 'nt':
            listed = subprocess.check_output(['tasklist', '/FI', f'PID eq {pid}', '/FO', 'CSV'], text=True)
            if f'"{pid}"' not in listed:
                break
        else:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
        await asyncio.sleep(0.05)
    else:
        pytest.fail(f'Chromium child {pid} survived cancellation')
    assert store.graph_revision() == 0
    next_job = service.enqueue('graphics-project', root, 'graphics', expected_revision=0,
                               params={'source': GOLDEN_SOURCE, 'duration_sec': 0.2, 'fps': 30})
    restarted = await service.wait(root, next_job.job_id)
    assert restarted.status == 'succeeded', restarted.error
    await service.shutdown()


def test_concurrent_source_workers_do_not_cancel_each_other(graphics_worker):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    barrier = Barrier(2)

    def compile_source(source):
        barrier.wait(timeout=5)
        return inspect_source(source)

    with ThreadPoolExecutor(max_workers=2) as pool:
        good = pool.submit(compile_source, DEFAULT_SOURCE)
        bad = pool.submit(compile_source, 'export default function Nope(){throw Error("bad");}')
        with pytest.raises(ValueError):
            bad.result(timeout=30)
        assert good.result(timeout=30)['scene']['width'] == 960


def test_encoder_timeout_reaps_child_and_allows_restart(tmp_path, monkeypatch):
    from open_edit.integrations.diffusion import graphics

    if not shutil.which('ffmpeg'):
        pytest.skip('FFmpeg required')
    real_popen = subprocess.Popen
    children = []

    def launch(*args, **kwargs):
        proc = real_popen(*args, **kwargs)
        children.append(proc)
        return proc

    monkeypatch.setattr(graphics.subprocess, 'Popen', launch)
    with pytest.raises(subprocess.TimeoutExpired):
        graphics._encode(['ffmpeg', '-v', 'error', '-re', '-f', 'lavfi', '-i',
                          'color=c=red:s=32x32:r=30', '-t', '60', '-f', 'null', '-'],
                         timeout=0.1, scratch=tmp_path)
    assert children[0].poll() is not None
    assert json.loads((tmp_path / 'encoder-process.json').read_text())['encoder'] == children[0].pid
    restarted = graphics._encode(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                                   'color=c=blue:s=32x32:r=30', '-t', '0.1', '-f', 'null', '-'],
                                  timeout=10)
    assert restarted.returncode == 0
