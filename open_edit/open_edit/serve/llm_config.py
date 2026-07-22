"""Per-project LLM provider + model config (v1.7).

Reads ``<project_dir>/.open_edit/config.toml`` to find an ``[llm]`` table:

.. code-block:: toml

    [llm]
    provider = "opencode"        # anthropic | openai | pi | opencode
    model = "opencode-go/minimax-m3"

    [llm.cli]
    # Adapter-specific overrides; reserved for future use.

If the file is missing or has no ``[llm]`` table, falls back to env vars:

- ``OPEN_EDIT_LLM_PROVIDER`` — must be one of ``anthropic|openai|pi|opencode``.
  Default: ``anthropic``.
- ``OPEN_EDIT_LLM_MODEL``   — model name passed to the adapter. Per-adapter
  default if unset (``claude-sonnet-4-5`` for anthropic, ``gpt-4o`` for
  openai, ``minimax-m3`` for pi, ``opencode-go/minimax-m3`` for opencode).

The provider ``antigravity`` is intentionally NOT in the enum. Antigravity
is a UI label in the chat frontend; the UI preset writes
``provider = "opencode"`` plus ``model = "omniroute/antigravity/<model>"``
into this file. The server never sees the string ``antigravity`` as a
provider value; it only appears as a model-name prefix inside the opencode
adapter.
"""
from __future__ import annotations

import contextlib
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class LLMConfigError(Exception):
    """Raised when the per-project LLM config is malformed."""


ProviderName = Literal["anthropic", "openai", "pi", "opencode"]


class LLMConfig(BaseModel):
    provider: ProviderName
    model: str
    cli: dict[str, str] = Field(default_factory=dict)

    @field_validator("model")
    @classmethod
    def _non_empty_model(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("model must be a non-empty string")
        return v.strip()


_PROVIDER_DEFAULT_MODEL: dict[str, str] = {
    "anthropic": "claude-sonnet-4-5",
    "openai": "gpt-4o",
    "pi": "minimax-m3",
    "opencode": "opencode-go/minimax-m3",
}


def _read_toml(path: Path) -> dict[str, Any]:
    """Read a TOML file. Python 3.11+ has tomllib; 3.13+ deprecated tomli."""
    try:
        import tomllib
    except ImportError:  # pragma: no cover — Python < 3.11
        import tomli as tomllib  # type: ignore[no-redef]
    with path.open("rb") as fh:
        return tomllib.load(fh)


def _atomic_write_text(path: Path, text: str) -> None:
    """Write text to path atomically via a temp file in the same dir."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".config.toml.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
        os.replace(tmp_name, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise


def _format_toml(cfg: LLMConfig) -> str:
    """Render LLMConfig as TOML. Keeps the format human-editable."""
    lines = ["[llm]"]
    lines.append(f'provider = "{cfg.provider}"')
    lines.append(f'model = "{cfg.model}"')
    if cfg.cli:
        lines.append("")
        lines.append("[llm.cli]")
        for k, v in sorted(cfg.cli.items()):
            lines.append(f'{k} = "{v}"')
    lines.append("")  # trailing newline
    return "\n".join(lines)


def load_llm_config(project_dir: Path) -> LLMConfig:
    """Load LLM config for a project, with env-var fallback.

    Resolution order:
    1. ``<project_dir>/.open_edit/config.toml`` — if it exists and contains
       an ``[llm]`` table, that wins (even if env vars are also set).
    2. Env vars ``OPEN_EDIT_LLM_PROVIDER`` and ``OPEN_EDIT_LLM_MODEL``.
    3. Per-provider hardcoded default model.
    """
    cfg_path = project_dir / ".open_edit" / "config.toml"
    file_cfg: dict[str, Any] = {}
    if cfg_path.is_file():
        try:
            data = _read_toml(cfg_path)
        except Exception as exc:
            raise LLMConfigError(
                f"failed to parse {cfg_path}: {exc}"
            ) from exc
        if isinstance(data, dict):
            file_cfg = data.get("llm") or {}
            if not isinstance(file_cfg, dict):
                raise LLMConfigError(
                    f"[llm] table in {cfg_path} must be a table, got {type(file_cfg).__name__}"
                )

    if file_cfg:
        provider = file_cfg.get("provider") or os.environ.get("OPEN_EDIT_LLM_PROVIDER", "anthropic")
        model = file_cfg.get("model") or os.environ.get("OPEN_EDIT_LLM_MODEL", "")
        cli = file_cfg.get("cli") or {}
        if not isinstance(cli, dict):
            raise LLMConfigError("[llm.cli] must be a table")
        cli = {str(k): str(v) for k, v in cli.items()}
    else:
        provider = os.environ.get("OPEN_EDIT_LLM_PROVIDER", "anthropic")
        env_model = os.environ.get("OPEN_EDIT_LLM_MODEL", "").strip()
        model = env_model or _PROVIDER_DEFAULT_MODEL.get(provider, "")
        cli = {}

    try:
        # Pydantic will validate ``provider`` is in the enum and raise
        # ValidationError if not. We catch and rewrap as LLMConfigError.
        return LLMConfig(provider=provider, model=model, cli=cli)  # type: ignore[arg-type]
    except Exception as exc:
        raise LLMConfigError(
            f"invalid LLM config: provider={provider!r}, model={model!r}: {exc}"
        ) from exc


def save_llm_config(project_dir: Path, cfg: LLMConfig) -> None:
    """Atomically write LLM config to ``<project_dir>/.open_edit/config.toml``.

    Preserves any non-``[llm]`` content already in the file (best-effort:
    we re-emit the [llm] table and discard unrelated content, with a stderr
    warning). For v1.7, this is acceptable — config.toml is new and we own
    its schema. A future version may add a merge-aware mode if needed.
    """
    cfg_path = project_dir / ".open_edit" / "config.toml"
    existing = ""
    if cfg_path.is_file():
        existing = cfg_path.read_text()
    if "[llm.cli]" in existing or "[" in existing.replace("[llm]", "").replace("\n", ""):
        print(
            f"warning: rewriting {cfg_path} — only [llm] table is preserved; "
            "other content is dropped",
            file=sys.stderr,
        )
    _atomic_write_text(cfg_path, _format_toml(cfg))
