"""Tests for the v1.7 LLM per-project config."""
from __future__ import annotations

from pathlib import Path

import pytest

from open_edit.serve.llm_config import (
    LLMConfig,
    LLMConfigError,
    load_llm_config,
    save_llm_config,
)


def test_load_llm_config_from_toml_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_dir = tmp_path / ".open_edit"
    cfg_dir.mkdir()
    (cfg_dir / "config.toml").write_text(
        '[llm]\nprovider = "opencode"\nmodel = "opencode-go/minimax-m3"\n'
    )
    # Even if env vars are set, the file wins.
    monkeypatch.setenv("OPEN_EDIT_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("OPEN_EDIT_LLM_MODEL", "claude-sonnet-4-5")
    cfg = load_llm_config(tmp_path)
    assert cfg.provider == "opencode"
    assert cfg.model == "opencode-go/minimax-m3"


def test_load_llm_config_falls_back_to_env_when_file_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPEN_EDIT_LLM_PROVIDER", "pi")
    monkeypatch.setenv("OPEN_EDIT_LLM_MODEL", "minimax-m3")
    cfg = load_llm_config(tmp_path)
    assert cfg.provider == "pi"
    assert cfg.model == "minimax-m3"


def test_load_llm_config_falls_back_to_env_when_file_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg_dir = tmp_path / ".open_edit"
    cfg_dir.mkdir()
    (cfg_dir / "config.toml").write_text("")
    monkeypatch.setenv("OPEN_EDIT_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("OPEN_EDIT_LLM_MODEL", "claude-sonnet-4-5")
    cfg = load_llm_config(tmp_path)
    assert cfg.provider == "anthropic"


def test_load_llm_config_validates_provider_enum(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg_dir = tmp_path / ".open_edit"
    cfg_dir.mkdir()
    (cfg_dir / "config.toml").write_text(
        '[llm]\nprovider = "antigravity"\nmodel = "x"\n'
    )
    monkeypatch.delenv("OPEN_EDIT_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("OPEN_EDIT_LLM_MODEL", raising=False)
    with pytest.raises(LLMConfigError, match="antigravity"):
        load_llm_config(tmp_path)


def test_load_llm_config_default_model_when_provider_set_no_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPEN_EDIT_LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPEN_EDIT_LLM_MODEL", raising=False)
    cfg = load_llm_config(tmp_path)
    assert cfg.provider == "openai"
    assert cfg.model == "gpt-4o"  # openai default per llm.py _model()


def test_save_llm_config_writes_atomic_file(tmp_path: Path) -> None:
    cfg = LLMConfig(provider="opencode", model="opencode-go/minimax-m3")
    save_llm_config(tmp_path, cfg)
    written = (tmp_path / ".open_edit" / "config.toml").read_text()
    assert "provider = \"opencode\"" in written
    assert "model = \"opencode-go/minimax-m3\"" in written
    # No leftover temp files.
    assert list((tmp_path / ".open_edit").glob("*.tmp")) == []


def test_save_then_load_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPEN_EDIT_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("OPEN_EDIT_LLM_MODEL", raising=False)
    cfg = LLMConfig(provider="pi", model="minimax-m3", cli={"foo": "bar"})
    save_llm_config(tmp_path, cfg)
    loaded = load_llm_config(tmp_path)
    assert loaded == cfg
