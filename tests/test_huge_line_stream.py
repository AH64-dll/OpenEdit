"""Exercise the actual CLI driver with local subprocesses and bounded output."""
from __future__ import annotations

import asyncio
import json
import sys

import pytest

from open_edit.serve.llm.cli.driver import _stream_cli


class ScriptAdapter:
    name = "test-cli"
    check_exit_status = True

    def __init__(self, script: str, timeout: float = 2):
        self.script = script
        self.default_timeout_s = timeout

    def build_command(self, **kwargs):
        return [sys.executable, "-u", "-c", self.script]

    async def stream_events(self, stdout):
        async for line in stdout:
            yield json.loads(line)


async def collect(adapter):
    return [event async for event in _stream_cli(
        adapter, "test", [{"role": "user", "content": "hello"}], [], "", None, None,
    )]


@pytest.mark.asyncio
async def test_driver_drains_large_stderr_and_emits_one_terminal_event():
    events = await collect(ScriptAdapter('''
import json, sys
sys.stderr.write("e" * (2 * 1024 * 1024))
print(json.dumps({"type": "text_delta", "text": "ok"}))
print(json.dumps({"type": "done", "stop_reason": "end_turn"}))
'''))
    assert events == [
        {"type": "text_delta", "text": "ok"},
        {"type": "done", "stop_reason": "end_turn"},
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("newline", [True, False])
async def test_oversized_line_is_bounded_and_child_is_reaped(monkeypatch, newline):
    processes = []
    original = asyncio.create_subprocess_exec

    async def track_process(*args, **kwargs):
        proc = await original(*args, **kwargs)
        processes.append(proc)
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", track_process)
    script = f'import sys, time; sys.stdout.write("A" * 2097152 + {chr(10) if newline else ""!r}); sys.stdout.flush(); time.sleep(60)'
    events = await collect(ScriptAdapter(script))
    assert any(event["type"] == "error" and "1 MiB" in event["message"] for event in events)
    assert events[-1] == {"type": "done", "stop_reason": "error"}
    assert processes[0].returncode is not None


@pytest.mark.asyncio
async def test_timeout_limits_total_lifetime_despite_continuous_output():
    events = await collect(ScriptAdapter('''
import json, time
for i in range(100):
    print(json.dumps({"type": "text_delta", "text": str(i)}), flush=True)
    time.sleep(0.03)
''', timeout=0.15))
    assert any(event["type"] == "error" and "timeout" in event["message"] for event in events)
    assert sum(event["type"] == "text_delta" for event in events) < 100
    assert sum(event["type"] == "done" for event in events) == 1
