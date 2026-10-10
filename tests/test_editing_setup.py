"""Readiness must explain missing tools without pulling agent or legacy runtimes in."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from open_edit.integrations import readiness as setup


def _tools(monkeypatch, tmp_path, *, node='v24.18.0', encoders='libx264', mlt=(7, 41, 0)):
    """Stub every probe so readiness is deterministic on any machine."""
    from open_edit.integrations.binaries import Resolved
    from open_edit.integrations.diffusion import compiler, graphics
    from open_edit.render import mlt_capability

    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setattr(setup.shutil, 'which', lambda name: f'/tools/{name}')
    monkeypatch.setattr(setup, '_output', lambda name, *args: encoders)
    monkeypatch.setattr(setup, 'resolve_node', lambda: Resolved('node', '/tools/node', 'path', node))
    monkeypatch.setattr(setup, 'resolve_npm', lambda: Resolved('npm', '/tools/npm', 'path'))
    monkeypatch.setattr(setup, 'resolve_melt', lambda: Resolved('melt', '/tools/melt', 'path', 'melt 7.41.0'))
    monkeypatch.setattr(setup, 'resolve_chromium', lambda: Resolved('chromium', '/pw/chrome', 'playwright'))
    monkeypatch.setattr(setup, 'resolve_hyperframes_browser',
                        lambda: Resolved('hyperframes-browser', '/hf/chrome', 'hyperframes'))
    monkeypatch.setattr(compiler, 'worker_problem', lambda: None)
    monkeypatch.setattr(graphics, 'graphics_problem', lambda: None)
    monkeypatch.setattr(mlt_capability, 'mlt_version', lambda: mlt)


def test_incomplete_ffmpeg_and_old_node_are_not_ready(monkeypatch, tmp_path):
    _tools(monkeypatch, tmp_path, node='v22.1.0', encoders='libvpx')
    checks = setup.readiness()
    assert not any(checks['capabilities'].values())
    assert 'libx264' in checks['checks'][0]['help']
    assert 'too old' in checks['checks'][2]['help'] and 'Node.js 24' in checks['checks'][2]['help']


def test_graphics_needs_browser_even_with_compiler(monkeypatch, tmp_path):
    from open_edit.integrations.binaries import Resolved

    _tools(monkeypatch, tmp_path)
    monkeypatch.setattr(setup, 'resolve_chromium', lambda: Resolved('chromium', None, 'missing'))
    result = setup.readiness()
    assert result['capabilities'] == {'timeline': True, 'media': True, 'graphics': False, 'audio_eq': True}
    graphics = next(check for check in result['checks'] if check['name'] == 'Editable graphics')
    assert graphics['help'] == 'No Chromium for graphics. Run: open_edit setup graphics'


def test_off_path_node_is_ready_and_explained(monkeypatch, tmp_path):
    from open_edit.integrations.binaries import Resolved

    _tools(monkeypatch, tmp_path)
    monkeypatch.setattr(setup, 'resolve_node', lambda: Resolved('node', '/nvm/node', 'nvm', 'v24.18.0'))
    result = setup.readiness()
    assert result['capabilities']['media'] and result['capabilities']['graphics']
    media = next(check for check in result['checks'] if check['name'].startswith('Clip properties'))
    assert 'via nvm; not on PATH' in media['detail'] and result['runtime']['node']['source'] == 'nvm'


def test_eq_readiness_discloses_unsupported_renderer_before_export(monkeypatch, tmp_path):
    _tools(monkeypatch, tmp_path, mlt=(7, 22, 0))
    result = setup.readiness()
    assert result['capabilities']['timeline'] and not result['capabilities']['audio_eq']
    check = next(check for check in result['checks'] if check['name'].startswith('Audio EQ'))
    assert not check['ready'] and '7.28' in check['help'] and '7.22' in check['name']


def test_review_startup_does_not_import_agent_modules():
    script = '''
import sys
import open_edit.serve.app
assert not any(name.startswith(('open_edit.serve.agent', 'open_edit.serve.providers',
    'open_edit.serve.ws.chat', 'open_edit.serve.llm')) for name in sys.modules)
'''
    result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


def test_legacy_dependencies_are_separate_and_locked():
    root = Path(__file__).parents[1]
    default = json.loads((root / 'package.json').read_text())
    lock = json.loads((root / 'package-lock.json').read_text())
    legacy = root / 'open_edit/integrations/remotion'
    package = json.loads((legacy / 'package.json').read_text())
    legacy_lock = json.loads((legacy / 'package-lock.json').read_text())
    assert not any('remotion' in key or key in ('react', 'react-dom') for key in default['dependencies'])
    assert not any(key.startswith('node_modules/@remotion/') for key in lock['packages'])
    assert package['dependencies']['remotion'] == '4.0.278'
    assert legacy_lock['packages']['']['dependencies'] == package['dependencies']
