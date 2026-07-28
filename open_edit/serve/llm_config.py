"""Per-project LLM provider + model config (v1.7).

Reads ``<project_dir>/.open_edit/config.toml`` to find an ``[llm]`` table:

.. code-block:: toml

    [llm]
    provider = "opencode"
    model = "opencode-go/minimax-m3"

    [llm.cli]
    # Adapter-specific overrides; reserved for future use.

The list of valid providers is defined in ``providers.py`` — the single
canonical registry.  Do not add a ``ProviderName`` literal here.
"""
from __future__ import annotations

import contextlib
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from .providers import (
    PROVIDERS,
    list_provider_ids,
    provider_default_model,
)


class LLMConfigError(Exception):
    """Raised when the per-project LLM config is malformed."""


class LLMConfig(BaseModel):
    provider: str
    model: str
    cli: dict[str, str] = Field(default_factory=dict)

    @field_validator("provider")
    @classmethod
    def _known_provider(cls, v: str) -> str:
        if v not in PROVIDERS:
            registered = ", ".join(sorted(PROVIDERS))
            raise ValueError(
                f"unknown provider {v!r}; expected one of: {registered}"
            )
        return v

    @field_validator("model")
    @classmethod
    def _non_empty_model(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("model must be a non-empty string")
        return v.strip()


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
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise


def _render_llm_toml(cfg: LLMConfig) -> str:
    """Render the ``[llm]`` table as TOML."""
    lines = ["[llm]"]
    lines.append(f'provider = "{cfg.provider}"')
    lines.append(f'model = "{cfg.model}"')
    if cfg.cli:
        lines.append("")
        lines.append("[llm.cli]")
        for k, v in sorted(cfg.cli.items()):
            lines.append(f'{k} = "{v}"')
    return "\n".join(lines)


def _strip_llm_section(text: str) -> str:
    """Return *text* with the ``[llm]`` section (and sub-tables) removed.

    Everything from a line matching ``[llm`` to the next ``[`` or EOF
    is stripped.  Lines before and after are preserved verbatim.
    """
    lines = text.splitlines(keepends=True)
    result: list[str] = []
    in_llm = False
    for line in lines:
        stripped = line.strip()
        if re.match(r"^\[llm(?:\.|\])", stripped):
            in_llm = True
            continue
        if in_llm and stripped.startswith("["):
            in_llm = False
        if not in_llm:
            result.append(line)
    return "".join(result)


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
        model = env_model or provider_default_model(provider)
        cli = {}

    try:
        return LLMConfig(provider=provider, model=model, cli=cli)
    except Exception as exc:
        raise LLMConfigError(
            f"invalid LLM config: provider={provider!r}, model={model!r}: {exc}"
        ) from exc


def save_llm_config(project_dir: Path, cfg: LLMConfig) -> None:
    """Atomically write LLM config to ``<project_dir>/.open_edit/config.toml``.

    Preserves any non-``[llm]`` content already in the file by stripping
    the old ``[llm]`` section and inserting the new one in its place.
    """
    cfg_path = project_dir / ".open_edit" / "config.toml"
    preamble = ""
    postamble = ""
    if cfg_path.is_file():
        existing = cfg_path.read_text()
        # Parse before modifying.  A malformed configuration may contain
        # valuable unrelated settings, so never turn it into a valid-looking
        # file by overwriting it with just an [llm] table.
        try:
            _read_toml(cfg_path)
        except Exception as exc:
            raise LLMConfigError(
                f"refusing to overwrite malformed configuration {cfg_path}: {exc}"
            ) from exc
        # Split at the first [llm line.
        match = re.search(r"(?m)^\[llm(?:\.|\])", existing)
        idx = match.start() if match else -1
        if idx >= 0:
            preamble = existing[:idx]
            rest = existing[idx:]
            postamble = _strip_llm_section(rest)
        else:
            preamble = existing.rstrip() + "\n\n"
            postamble = ""
    new_llm = _render_llm_toml(cfg)
    merged = preamble + new_llm + "\n" + postamble
    if postamble and not postamble.endswith("\n"):
        merged += "\n"
    _atomic_write_text(cfg_path, merged)
