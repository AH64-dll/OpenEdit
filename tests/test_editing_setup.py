"""Readiness must explain missing tools without pulling agent or legacy runtimes in."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from open_edit.integrations import readiness as setup


def test_incomplete_ffmpeg_and_old_node_are_not_ready(monkeypatch):
    monkeypatch.setattr(setup.shutil, 'which', lambda name: f'/tools/{name}')
    monkeypatch.setattr(setup, '_output', lambda name, *args: 'v22.1.0' if name == 'node' else 'libvpx')
    checks = setup.readiness()
    assert not any(checks['capabilities'].values())
    assert 'libx264' in checks['checks'][0]['help']
    assert 'Node.js 24' in checks['checks'][2]['help']


def test_graphics_needs_browser_even_with_compiler(monkeypatch):
    from open_edit.integrations.diffusion import compiler, graphics
    from open_edit.render import mlt_capability

    monkeypatch.setattr(setup.shutil, 'which', lambda name: f'/tools/{name}')
    monkeypatch.setattr(setup, '_output', lambda name, *args: 'v24.18.0' if name == 'node' else 'libx264')
    monkeypatch.setattr(compiler, 'worker_ready', lambda: True)
    monkeypatch.setattr(graphics, 'graphics_ready', lambda: True)
    monkeypatch.setattr(setup, 'chromium_available', lambda: False)
    monkeypatch.setattr(mlt_capability, 'mlt_version', lambda: (7, 41, 0))
    assert setup.readiness()['capabilities'] == {'timeline': True, 'media': True, 'graphics': False, 'audio_eq': True}


def test_eq_readiness_discloses_unsupported_renderer_before_export(monkeypatch):
    from open_edit.render import mlt_capability

    monkeypatch.setattr(setup.shutil, 'which', lambda name: f'/tools/{name}')
    monkeypatch.setattr(setup, '_output', lambda name, *args: 'v24.18.0' if name == 'node' else 'libx264')
    monkeypatch.setattr(mlt_capability, 'mlt_version', lambda: (7, 22, 0))
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
