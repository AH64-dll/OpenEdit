"""Tests for the AgentAdapter protocol and PiAgentAdapter."""
import asyncio
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[0]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import agent_adapters as aa
from agent_adapters import OpenCodeAdapter, PiAgentAdapter


def test_piagent_adapter_list_models(tmp_path, monkeypatch):
    models_file = tmp_path / "models-store.json"
    models_file.write_text(
        '{"opencode-go": {"models": ['
        '{"id":"minimax-m3","name":"MiniMax M3"},'
        '{"id":"deepseek-v4-pro","name":"DeepSeek V4 Pro"}]}}'
    )
    monkeypatch.setattr(aa, "MODELS_STORE_PATH", models_file)

    adapter = PiAgentAdapter(
        model="minimax-m3",
        project="/x/y.kdenlive",
        session_id="s1",
        pi_args=[],
    )
    assert adapter.list_models() == [
        {"id": "minimax-m3", "name": "MiniMax M3"},
        {"id": "deepseek-v4-pro", "name": "DeepSeek V4 Pro"},
    ]


def test_opencode_adapter_list_models(monkeypatch):
    captured = {}
    def fake_run(cmd):
        captured["cmd"] = cmd
        return "opencode-go/minimax-m3\nopencode-go/deepseek-v4-pro\n\nopenai/gpt-5.5\n"
    adapter = aa.OpenCodeAdapter(
        model="opencode-go/minimax-m3", project="/x/y.kdenlive",
        session_id="s2", models_cmd_fn=fake_run,
    )
    models = adapter.list_models()
    assert models == [
        {"id": "opencode-go/minimax-m3", "name": "opencode-go/minimax-m3"},
        {"id": "opencode-go/deepseek-v4-pro", "name": "opencode-go/deepseek-v4-pro"},
        {"id": "openai/gpt-5.5", "name": "openai/gpt-5.5"},
    ]
    assert captured["cmd"] == ["opencode", "models"]


def test_opencode_adapter_run_prompt_injectable():
    class _FakeStdout:
        def __init__(self, lines):
            self._lines = lines
            self._idx = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self._idx >= len(self._lines):
                raise StopAsyncIteration
            line = self._lines[self._idx]
            self._idx += 1
            return line

    class _FakeProc:
        def __init__(self, lines):
            self.stdout = _FakeStdout(lines)
            self.returncode = None

        async def wait(self):
            self.returncode = 0
            return 0

        def kill(self):
            self.returncode = -9

    lines = [
        b'{"type":"assistant","message":{"content":"hello"}}\n',
        b'{"tool":"read","args":{"path":"/x"}}\n',
    ]

    async def fake_run_cmd(cmd):
        return _FakeProc(lines)

    adapter = OpenCodeAdapter(
        model="minimax-m3", project="/x/y.kdenlive",
        session_id="s3", run_cmd_fn=fake_run_cmd,
    )

    async def _run():
        events = [ev async for ev in adapter.run_prompt("hi")]
        assert any(
            ev.kind == "message_delta" and ev.role == "assistant" and ev.text == "hello"
            for ev in events
        ), events
        assert any(ev.kind == "tool" and ev.tool == "read" for ev in events), events
        assert any(ev.kind == "done" for ev in events), events

    asyncio.run(_run())


def test_build_adapter_and_list_apps():
    # build_adapter dispatches by id
    p = aa.build_adapter("piagent", "test-provider/test-model", "/x/y.kdenlive", "s9")
    assert isinstance(p, aa.PiAgentAdapter)
    o = aa.build_adapter("opencode", "opencode-go/minimax-m3", "/x/y.kdenlive", "s9")
    assert isinstance(o, aa.OpenCodeAdapter)
    # unknown id raises
    import pytest
    with pytest.raises(ValueError):
        aa.build_adapter("nope", "m", "/x", "s")


def test_list_apps_marks_antigravity_unavailable(monkeypatch):
    apps = aa.list_apps()
    by_id = {a["id"]: a for a in apps}
    assert by_id["piagent"]["available"] is True
    assert by_id["opencode"]["available"] is True
    assert by_id["antigravity"]["available"] is False
    assert by_id["antigravity"]["models"] == []
    # list_apps must not shell anything -> no exception, returns 3 entries
    assert len(apps) == 3
