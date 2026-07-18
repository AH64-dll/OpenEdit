"""Tests for the AgentAdapter protocol and PiAgentAdapter."""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[0]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import agent_adapters as aa
from agent_adapters import PiAgentAdapter


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
