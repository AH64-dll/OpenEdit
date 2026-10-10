"""Runtime binaries are found off PATH (nvm Node, OpenEdit/Shotcut melt) and reported precisely."""
from __future__ import annotations

import asyncio
import os
import stat
from pathlib import Path
from unittest import mock

import pytest

from open_edit.integrations import binaries

pytestmark = pytest.mark.skipif(os.name == 'nt', reason='POSIX shell stubs')


def _stub(path: Path, output: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'#!/bin/sh\necho "{output}"\n')
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


@pytest.fixture
def bare_env(tmp_path, monkeypatch):
    """A host-launched process: empty PATH, no overrides, HOME with managed installs."""
    home = tmp_path / 'home'
    empty = tmp_path / 'empty-bin'
    empty.mkdir()
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setenv('PATH', str(empty))
    for var in ('NVM_DIR', 'FNM_DIR', 'OPEN_EDIT_NODE_BIN', 'OPEN_EDIT_MELT', 'OPEN_EDIT_CHROMIUM',
                'PLAYWRIGHT_BROWSERS_PATH', 'XDG_CACHE_HOME', 'HYPERFRAMES_BROWSER_PATH'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(binaries, '_ADDED', [])
    return home


def test_nvm_node_off_path_is_found_newest_usable_first(bare_env):
    _stub(bare_env / '.nvm/versions/node/v20.11.0/bin/node', 'v20.11.0')
    newest = _stub(bare_env / '.nvm/versions/node/v24.18.0/bin/node', 'v24.18.0')
    _stub(newest.with_name('npm'), '10.0.0')
    node = binaries.resolve_node()
    assert (node.path, node.source, node.version) == (str(newest), 'nvm', 'v24.18.0')
    assert binaries.resolve_npm().path == str(newest.with_name('npm'))
    assert binaries.node_bin() == str(newest)


def test_old_node_only_is_not_usable(bare_env):
    _stub(bare_env / '.nvm/versions/node/v20.11.0/bin/node', 'v20.11.0')
    assert binaries.node_bin() is None


def test_invalid_override_never_falls_back(bare_env, monkeypatch):
    _stub(bare_env / '.nvm/versions/node/v24.18.0/bin/node', 'v24.18.0')
    monkeypatch.setenv('OPEN_EDIT_NODE_BIN', str(bare_env / 'missing-node'))
    node = binaries.resolve_node()
    assert node.path is None and node.source == 'env:OPEN_EDIT_NODE_BIN'
    monkeypatch.setenv('OPEN_EDIT_MELT', str(bare_env / 'missing-melt'))
    assert binaries.melt_bin() is None


def test_openedit_runtime_melt_and_path_injection(bare_env):
    melt = _stub(bare_env / '.local/share/OpenEdit/runtime/bin/melt', 'melt 7.41.0')
    node = _stub(bare_env / '.nvm/versions/node/v24.18.0/bin/node', 'v24.18.0')
    resolved = binaries.resolve_melt()
    assert (resolved.path, resolved.source, resolved.version) == (str(melt), 'open_edit', 'melt 7.41.0')
    added = binaries.ensure_runtime_path()
    assert added == [str(node.parent), str(melt.parent)]
    assert os.environ['PATH'].split(os.pathsep)[:2] == added
    assert binaries.ensure_runtime_path() == []
    assert binaries.resolve_melt().source == 'path'


def test_system_chrome_is_reported_but_not_used_silently(bare_env, monkeypatch):
    from open_edit.integrations import readiness

    monkeypatch.setattr(binaries, '_SYSTEM_CHROME', (str(_stub(bare_env / 'chrome', 'Chrome 1')),))
    assert binaries.resolve_chromium().source == 'system'
    assert readiness.chromium_available() is False
    monkeypatch.setenv('OPEN_EDIT_CHROMIUM', str(bare_env / 'chrome'))
    assert readiness.chromium_available() is True


def test_get_readiness_query_is_compact(tmp_path, monkeypatch):
    from open_edit.integrations import readiness
    from open_edit.kernel.pillar_tools import dispatch_query

    full = {'capabilities': {'timeline': False}, 'checks': [
        {'name': 'Timeline preview and export', 'ready': False, 'help': 'install melt', 'detail': 'melt: not found'},
        {'name': 'Hardware video encoding (optional)', 'ready': False, 'help': 'x', 'detail': 'y'},
        {'name': 'Video and audio tools', 'ready': True, 'help': 'z', 'detail': 'ok'}]}
    monkeypatch.setattr(readiness, 'readiness', lambda: full)
    result = dispatch_query('get_readiness', {}, tmp_path)
    assert result == {'status': 'ok', 'capabilities': {'timeline': False}, 'ready': False,
                      'needs_setup': [{'name': 'Timeline preview and export', 'fix': 'install melt',
                                       'found': 'melt: not found'}],
                      'optional_unavailable': ['Hardware video encoding (optional)']}
    assert dispatch_query('get_readiness', {'detail': True}, tmp_path)['checks'] == full['checks']


@pytest.mark.render_preflight
def test_trigger_render_without_melt_fails_before_queueing(tmp_path, monkeypatch):
    from open_edit.kernel.tool_executor import execute_trigger_render

    monkeypatch.setenv('OPEN_EDIT_MELT', str(tmp_path / 'missing-melt'))
    service = mock.MagicMock()
    with mock.patch('open_edit.kernel.render_jobs.DEFAULT_RENDER_JOB_SERVICE', service):
        result = asyncio.run(execute_trigger_render(args={'mode': 'proxy'}, project_path=tmp_path))
    assert result['ok'] is False and result['error_code'] == 'missing_dependency'
    assert 'melt' in result['error'] and 'get_readiness' in result['hint']
    service.enqueue.assert_not_called()
