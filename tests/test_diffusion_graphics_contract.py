"""Contract tests for parent_id stamping and cumulative graphics asset budgets."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

import open_edit.integrations.diffusion.graphics as graphics_module
from open_edit.integrations.diffusion.graphics import browser_directory, materialize
from open_edit.ir.types import Asset


def _node() -> str | None:
    node = shutil.which('node')
    if node:
        return node
    nvm = sorted(Path.home().glob('.nvm/versions/node/*/bin/node'))
    return str(nvm[-1]) if nvm else None


def _parse(source: str, tmp_path: Path) -> dict:
    """Run the real pinned compiler's parse() and return its document."""
    directory = browser_directory()
    node = _node()
    compiler = directory / 'compile.cjs'
    if not node or not (directory / 'node_modules/@babel/core').is_dir() or not compiler.is_file():
        pytest.skip('Node or the pinned browser dependencies are not installed')
    script = tmp_path / 'source.tsx'
    script.write_text(source)
    run = subprocess.run(
        [node, '-e',
         'const { parse } = require(process.argv[1]);'
         'const fs = require("node:fs");'
         'process.stdout.write(JSON.stringify(parse(fs.readFileSync(process.argv[2], "utf8"))));',
         str(compiler), str(script)],
        capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


NESTED_SOURCE = '''export default function Graphics() {
  return <stage id="board"><scene id="main" width={960} height={540}>
    <rect id="background" width={960} height={540} fill="#000000"/>
    <group id="card" x={10} y={20}>
      <rect id="inner" width={100} height={50}><animation id="fadeIn" type="fade" phase="in" duration={0.5}/></rect>
      <text id="caption" fontFamily="OpenEdit Sans" fontSize={32}>Hi</text>
    </group>
    <sequence id="seq"><image id="pic" src="asset://''' + 'a' * 64 + '''" transition={{type:"dissolve",duration:0.4}}/></sequence>
    <rect id="clip" clipPath={true} width={200} height={200}>
      <rect id="masked" width={50} height={50}/><solidPaint id="paint" color="#ff0000"/>
    </rect>
    <rect id="keyed" width={10} height={10}><keyframeTrack id="track" property="x"><keyframe id="k0" time={0} value={0}/></keyframeTrack></rect>
  </scene></stage>;
}'''


def test_parse_stamps_each_element_with_its_direct_jsx_parent(tmp_path):
    document = _parse(NESTED_SOURCE, tmp_path)
    assert {e['id']: e['parent_id'] for e in document['elements']} == {
        'board': None, 'main': 'board', 'background': 'main', 'card': 'main',
        'inner': 'card', 'fadeIn': 'inner', 'caption': 'card',
        'seq': 'main', 'pic': 'seq', 'clip': 'main', 'masked': 'clip',
        'paint': 'clip', 'keyed': 'main', 'track': 'keyed', 'k0': 'track'}
    # Exactly the direct scene children are canvas-selectable/draggable.
    scene_id = document['scene']['id']
    assert scene_id == 'main'
    assert {e['id'] for e in document['elements'] if e['parent_id'] == scene_id} == {
        'background', 'card', 'seq', 'clip', 'keyed'}


def test_parse_rejects_a_forged_parent_id_property(tmp_path):
    source = NESTED_SOURCE.replace('<rect id="inner"', '<rect id="inner" parent_id="main"')
    node = _node()
    directory = browser_directory()
    if not node or not (directory / 'node_modules/@babel/core').is_dir():
        pytest.skip('Node or the pinned browser dependencies are not installed')
    script = tmp_path / 'source.tsx'
    script.write_text(source)
    run = subprocess.run(
        [node, '-e',
         'const { parse } = require(process.argv[1]);'
         'const fs = require("node:fs");'
         'process.stdout.write(JSON.stringify(parse(fs.readFileSync(process.argv[2], "utf8"))));',
         str(directory / 'compile.cjs'), str(script)],
        capture_output=True, text=True, timeout=30)
    assert run.returncode != 0
    assert 'parent_id' in run.stderr


def _image_asset(hash_: str, width: int | None = 100, height: int | None = 100) -> Asset:
    return Asset(asset_hash=hash_, original_path=f'{hash_}.png',
                 stored_path=f'{hash_}.png', type='image',
                 width=width, height=height)


def _cas_file(root: Path, hash_: str, size: int) -> None:
    path = root / '.open_edit' / 'assets' / hash_[:2] / hash_
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('wb') as handle:
        handle.truncate(size)


@pytest.fixture
def graphics_project(tmp_path):
    root = tmp_path / 'graphics-project'
    (root / '.open_edit').mkdir(parents=True)
    return root


def _stub_assets(monkeypatch, root: Path, assets: list[Asset], sizes: dict[str, int]) -> None:
    """Pin CAS contents and a deterministic document without the browser worker."""
    for hash_, size in sizes.items():
        _cas_file(root, hash_, size)
    monkeypatch.setattr(graphics_module, 'list_assets_from_disk', lambda _root: assets)
    monkeypatch.setattr(graphics_module, '_hash_file', lambda path: Path(path).name)
    monkeypatch.setattr(graphics_module, 'inspect_source', lambda _source: {
        'scene': {'id': 'main', 'width': 960, 'height': 540}, 'elements': [],
        'assets': sorted(a.asset_hash for a in assets)})
    monkeypatch.setattr(graphics_module, '_runtime_digest', lambda: 'digest')


def test_materialize_rejects_over_64_mib_total(graphics_project, monkeypatch):
    hashes = [f'{i:064x}' for i in range(3)]
    _stub_assets(monkeypatch, graphics_project, [_image_asset(h) for h in hashes],
                 {hashes[0]: 32 * 1024 * 1024, hashes[1]: 32 * 1024 * 1024, hashes[2]: 1})
    with pytest.raises(ValueError, match='budget'):
        materialize(graphics_project, {'source': 'x', 'duration_sec': 1, 'fps': 30})


def test_materialize_rejects_over_32_megapixels_total(graphics_project, monkeypatch):
    hashes = [f'{i + 3:064x}' for i in range(3)]
    _stub_assets(monkeypatch, graphics_project,
                 [_image_asset(h, width=5000, height=2500) for h in hashes],
                 dict.fromkeys(hashes, 100))
    with pytest.raises(ValueError, match='budget'):
        materialize(graphics_project, {'source': 'x', 'duration_sec': 1, 'fps': 30})


def test_materialize_rejects_the_65th_image(graphics_project, monkeypatch):
    hashes = [f'{i + 100:064x}' for i in range(65)]
    _stub_assets(monkeypatch, graphics_project, [_image_asset(h) for h in hashes],
                 dict.fromkeys(hashes, 1))
    with pytest.raises(ValueError, match='budget'):
        materialize(graphics_project, {'source': 'x', 'duration_sec': 1, 'fps': 30})


@pytest.mark.parametrize('width,height', [(None, 100), (0, 100), (100, None), (100, 0)])
def test_materialize_rejects_images_without_probed_dimensions(graphics_project, monkeypatch,
                                                              width, height):
    """Unprobeable images MUST NOT bypass the pixel budget as zero-sized."""
    hash_ = 'cd' * 32
    _stub_assets(monkeypatch, graphics_project, [_image_asset(hash_, width, height)], {hash_: 10})
    with pytest.raises(ValueError, match='dimensions'):
        materialize(graphics_project, {'source': 'x', 'duration_sec': 1, 'fps': 30})


def test_materialize_accepts_exactly_at_budget_boundaries(graphics_project, monkeypatch):
    """64 images totaling exactly 64 MiB stay inside all three budgets."""
    hashes = [f'{i + 1000:064x}' for i in range(64)]
    _stub_assets(monkeypatch, graphics_project, [_image_asset(h, width=512, height=512) for h in hashes],
                 dict.fromkeys(hashes, 1024 * 1024))
    completed = subprocess.CompletedProcess([], 0, 'ffmpeg version fake\n', '')
    monkeypatch.setattr(graphics_module.subprocess, 'run', lambda *a, **k: completed)

    class BudgetStageError(Exception):
        pass

    def halt(*_args, **_kwargs):
        raise BudgetStageError()

    monkeypatch.setattr(graphics_module, '_worker', halt)
    with pytest.raises(BudgetStageError):
        materialize(graphics_project, {'source': 'x', 'duration_sec': 1, 'fps': 30})


def test_materialize_cache_hit_rewrites_preview_paths(graphics_project, monkeypatch):
    """A moved project's cached record MUST repoint poster/preview at its own cache."""
    hash_ = 'ab' * 32
    _stub_assets(monkeypatch, graphics_project, [_image_asset(hash_)], {hash_: 100})
    completed = subprocess.CompletedProcess([], 0, 'ffmpeg version fake\n', '')
    monkeypatch.setattr(graphics_module.subprocess, 'run', lambda *a, **k: completed)
    params = {'source': 'x', 'duration_sec': 1, 'fps': 30}
    key = hashlib.sha256(json.dumps(
        {'protocol': 1, 'source': 'x', 'duration_sec': 1.0, 'fps': 30,
         'runtime': 'digest', 'assets': [hash_], 'ffmpeg': 'ffmpeg version fake'},
        sort_keys=True).encode()).hexdigest()
    cache = graphics_project / '.open_edit' / 'graphics'
    cache.mkdir(parents=True)
    (cache / f'{key}.png').write_bytes(b'png')
    (cache / f'{key}.webm').write_bytes(b'webm')
    stale = f'/moved-project/.open_edit/graphics/{key}'
    record = {'asset_hash': hash_, 'content_key': key, 'duration_sec': 1.0, 'fps': 30,
              'scene': {'id': 'main', 'width': 960, 'height': 540},
              'elements': [{'tag': 'rect', 'id': 'r', 'parent_id': 'main'}],
              'upstream': graphics_module.UPSTREAM,
              'poster_path': f'{stale}.png', 'preview_path': f'{stale}.webm'}
    (cache / f'{key}.json').write_text(json.dumps(record))
    result = materialize(graphics_project, params)
    assert result['ok'] and result['cache_hit']
    assert result['poster_path'] == str(cache / f'{key}.png')
    assert result['preview_path'] == str(cache / f'{key}.webm')
    assert result['output_path'] == str(graphics_project / '.open_edit' / 'assets' / hash_[:2] / hash_)
    assert json.loads((cache / 'last-good.json').read_text()) == {'content_key': key}
