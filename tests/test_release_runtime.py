"""Installer environment activation and generated agent configurations."""
from __future__ import annotations

import json
import os
import sys
import tomllib

import pytest

from open_edit.mcp.config import host_config
from open_edit.runtime import activate


def test_host_configs_keep_venv_and_escape_project_paths(tmp_path):
    project = tmp_path / 'project with spaces'
    (project / '.open_edit').mkdir(parents=True)
    config = json.loads(host_config(project))['mcpServers']['openedit']
    assert config['command'] == os.path.abspath(sys.executable)
    assert config['args'][-1] == str(project.resolve())
    native = json.loads(host_config(project, 'opencode'))['mcp']['openedit']
    assert native['command'] == [config['command'], *config['args']]
    codex = tomllib.loads(host_config(project, 'codex'))['mcp_servers']['openedit']
    assert codex == config


def test_runtime_prefix_is_idempotent_and_respects_explicit_overrides(tmp_path, monkeypatch):
    folder = tmp_path / 'runtime bin'
    folder.mkdir()
    (tmp_path / '.openedit-runtime.json').write_text(json.dumps({
        'version': 1, 'path': [str(folder)], 'environment': {'MLT_REPOSITORY': 'installed'}}))
    monkeypatch.setattr(sys, 'prefix', str(tmp_path / '.venv'))
    monkeypatch.setenv('PATH', os.defpath)
    monkeypatch.setenv('MLT_REPOSITORY', 'user-selected')
    activate()
    first = os.environ['PATH']
    activate()
    assert os.environ['PATH'] == first
    assert first.split(os.pathsep)[0] == str(folder)
    assert os.environ['MLT_REPOSITORY'] == 'user-selected'


def test_invalid_runtime_config_fails_instead_of_silent_partial_setup(tmp_path, monkeypatch):
    (tmp_path / '.openedit-runtime.json').write_text('{"version": 999}')
    monkeypatch.setattr(sys, 'prefix', str(tmp_path / '.venv'))
    with pytest.raises(RuntimeError, match='rerun the installer'):
        activate()
