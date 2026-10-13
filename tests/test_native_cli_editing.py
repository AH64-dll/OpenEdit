"""Native CLI editing contract and project-specific MCP connection tests."""
import json
import os
import sys

import pytest

from open_edit.serve.cli_adapter import get_adapter
from open_edit.serve.llm.cli.driver import _stream_cli
from open_edit.serve.opencode_adapter import normalize_opencode_line


def test_opencode_completed_mcp_edit_is_visible():
    events = normalize_opencode_line(json.dumps({"type": "tool_use", "part": {
        "id": "edit1", "tool": "openedit_edit_project", "state": {
            "status": "completed", "input": {"operation": "apply_graphics_edits"},
            "output": json.dumps({"status": "ok", "graph_revision": 3})}}}))
    assert [event["type"] for event in events] == ["tool_use", "tool_result"]
    assert events[1]["result"]["graph_revision"] == 3
    assert events[0]["name"] == "edit_project"


@pytest.mark.asyncio
async def test_opencode_receives_project_mcp_and_preserves_user_config(tmp_path, monkeypatch):
    binary = tmp_path / 'opencode'
    binary.write_text("""#!/usr/bin/env python3
import json, os, pathlib, sys
pathlib.Path('received-config.json').write_text(os.environ['OPENCODE_CONFIG_CONTENT'])
print(json.dumps({'type':'text','part':{'text':'Connected'}}))
""")
    binary.chmod(0o755)
    monkeypatch.setenv('PATH', str(tmp_path) + os.pathsep + os.environ.get('PATH', ''))
    monkeypatch.setenv('OPENCODE_CONFIG_CONTENT', json.dumps({'theme':'opencode', 'mcp': {'other': {'type':'remote','url':'https://example.com/mcp'}}}))
    events = [event async for event in _stream_cli(get_adapter('opencode'), 'test/model',
        [{'role':'user','content':'Edit'}], [], 'Use OpenEdit', None, str(tmp_path))]
    config = json.loads((tmp_path / 'received-config.json').read_text())
    connection = config['mcp']['openedit']
    assert connection['command'][-2:] == ['--project', str(tmp_path)]
    assert connection['command'][0] == sys.executable
    assert config['mcp']['other']['url'] == 'https://example.com/mcp'
    assert config['agent']['openedit']['permission']['openedit_*'] == 'allow'
    assert events[-1]['stop_reason'] == 'end_turn'


@pytest.mark.asyncio
async def test_cli_error_remains_failure_after_text(tmp_path, monkeypatch):
    binary = tmp_path / 'opencode'
    binary.write_text("""#!/usr/bin/env python3
import json
print(json.dumps({'type':'text','part':{'text':'Starting'}}))
print(json.dumps({'type':'error','error':{'data':{'message':'Authentication failed'}}}))
print(json.dumps({'type':'step_finish','part':{'reason':'stop'}}))
raise SystemExit(1)
""")
    binary.chmod(0o755)
    monkeypatch.setenv('PATH', str(tmp_path) + os.pathsep + os.environ.get('PATH', ''))
    events = [event async for event in _stream_cli(get_adapter('opencode'), 'test/model',
        [{'role':'user','content':'Edit'}], [], 'Use OpenEdit', None, str(tmp_path))]
    assert any(event['type'] == 'error' for event in events)
    assert events[-1] == {'type':'done','stop_reason':'error'}
