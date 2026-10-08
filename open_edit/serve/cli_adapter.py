"""Optional CLI chat adapters. External editing harnesses use the MCP server."""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

from .opencode_adapter import normalize_opencode_line


@runtime_checkable
class CLIAdapter(Protocol):
    """One CLI backend. Stateless; methods only."""

    name: str
    default_timeout_s: int
    check_exit_status: bool

    def default_model(self) -> str: ...
    def available_models(self) -> list[str]: ...
    def supports_tools(self) -> bool: ...
    def supports_images(self) -> bool: ...
    def manages_own_auth(self) -> bool: ...
    def build_command(
        self,
        model: str,
        user_text: str,
        session_id: str,
        system_prompt: str,
        project_path: str | None = None,
    ) -> list[str]: ...
    def normalize_event(self, line: str) -> list[dict[str, Any]]: ...
    async def stream_events(
        self,
        stdout: AsyncIterator[bytes],
    ) -> AsyncIterator[dict[str, Any]]: ...


class _BaseCLIAdapter:
    """Shared defaults so SDK stubs and plain-text adapters stay tiny.

    Model list, defaults, and tool/image capabilities are derived from
    the canonical :data:`open_edit.serve.providers.PROVIDERS` registry —
    an adapter holds only CLI-specific behavior (command construction,
    event normalization, auth).
    """

    check_exit_status = False

    def _spec(self):
        from .providers import PROVIDERS
        return PROVIDERS[self.name]

    def default_model(self) -> str:
        return self._spec().default_model

    def available_models(self) -> list[str]:
        return list(self._spec().models)

    def supports_tools(self) -> bool:
        return self._spec().supports_tools

    def supports_images(self) -> bool:
        return self._spec().supports_images


    def normalize_event(self, line: str) -> list[dict[str, Any]]:
        return []

    async def stream_events(
        self,
        stdout: AsyncIterator[bytes],
    ) -> AsyncIterator[dict[str, Any]]:
        """Default: decode each stdout line and map it via ``normalize_event``.

        Lines are NOT stripped — adapters that care (opencode) strip
        themselves; antigravity preserves the raw line (incl. newline)
        exactly as the pre-refactor driver yielded it.
        """
        async for raw in stdout:
            for ev in self.normalize_event(raw.decode("utf-8", errors="replace")):
                yield ev


# --- provider-specific helpers -----------------------------------------





# --- opencode adapter: cheap shell-out to `opencode models` -----------

_OPENCODE_CACHE: dict[str, tuple[float, list[str]]] = {}
_OPENCODE_CACHE_TTL_S = 60.0


def _opencode_models_via_cli() -> list[str]:
    """Run ``opencode models`` and return the list of model ids.

    Cached for 60s. If the binary is missing or fails, returns []. Never
    raises — the dropdown can show an empty list rather than 500ing the
    project config page.
    """
    now = time.monotonic()
    cached = _OPENCODE_CACHE.get("__all__")
    if cached is not None and (now - cached[0]) < _OPENCODE_CACHE_TTL_S:
        return list(cached[1])
    bin_path = shutil.which("opencode")
    if bin_path is None:
        return []
    try:
        out = subprocess.run(
            [bin_path, "models"],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if out.returncode != 0:
        return []
    models: list[str] = []
    for line in out.stdout.splitlines():
        line = line.strip()
        # The CLI output is a mix of headers and one model per line. We
        # accept lines that look like "<provider>/<model>" or
        # "<provider>/<provider>/<model>" (three-segment for omniroute).
        if not line or line.startswith(("┌", "│", "└", "─")) or " " in line:
            continue
        if "/" in line and line.count("/") in (1, 2):
            models.append(line)
    _OPENCODE_CACHE["__all__"] = (now, models)
    return list(models)


# --- adapter implementations ------------------------------------------







class _OpenCodeAdapter(_BaseCLIAdapter):
    name = "opencode"
    default_timeout_s = 3600

    def available_models(self) -> list[str]:
        """Shell out to ``opencode models`` for live discovery."""
        return _opencode_models_via_cli()

    def manages_own_auth(self) -> bool:
        return True  # reads ~/.local/share/opencode/auth.json

    def build_command(
        self,
        model: str,
        user_text: str,
        session_id: str,
        system_prompt: str,
        project_path: str | None = None,
    ) -> list[str]:
        # opencode has no --append-system-prompt flag; we prepend the
        # system prompt to the user message so the model still sees it.
        # When user_text is already role-tagged (full_history strategy),
        # do not wrap it again in a second [user] envelope.
        body = user_text if user_text.lstrip().startswith("[") else f"[user]\n{user_text}"
        full_message = f"[system]\n{system_prompt}\n\n{body}"
        cmd = [
            "opencode",
            "run",
            "--format", "json",
            "--model", model,
            full_message,
        ]
        return cmd

    def normalize_event(self, line: str) -> list[dict[str, Any]]:
        """Map one raw opencode stdout line to 0..n StreamEvents.

        Delegates to the shared normalizer in ``opencode_adapter.py``
        (also used by ``parse_opencode_events`` for the test surface).
        """
        return normalize_opencode_line(line)


class _JCodeAdapter(_BaseCLIAdapter):
    """JCode CLI — ``--json`` emits a single JSON blob, not a line stream.

    Hidden provider (chat_only, stateless). The blob is parsed for a
    reply string (``text`` / ``response`` / ``content`` or OpenAI-style
    ``choices[0].message.content``); anything else is passed through
    as a single ``text_delta``. The driver's trailing ``done`` closes
    the turn.
    """
    name = "jcode"
    default_timeout_s = 3600

    def manages_own_auth(self) -> bool:
        return True  # reads ~/.jcode/auth.json

    def build_command(
        self,
        model: str,
        user_text: str,
        session_id: str,
        system_prompt: str,
        project_path: str | None = None,
    ) -> list[str]:
        jcode_bin = shutil.which("jcode") or "jcode"
        body = user_text if user_text.lstrip().startswith("[") else f"[user]\n{user_text}"
        full_message = f"[system]\n{system_prompt}\n\n{body}"
        return [jcode_bin, "--print", full_message, "--model", model, "--json"]

    async def stream_events(
        self,
        stdout: AsyncIterator[bytes],
    ) -> AsyncIterator[dict[str, Any]]:
        """Accumulate the whole stdout blob, then emit the reply text.

        Matches the pre-refactor jcode branch: the entire output is
        parsed as one JSON document; the extracted reply (or the raw
        text fallback) is yielded as a single ``text_delta``. The
        driver emits the terminal ``done``.
        """
        raw = b""
        async for chunk in stdout:
            raw += chunk
        jcode_text = raw.decode("utf-8", errors="replace").strip()
        if jcode_text:
            try:
                jcode_obj = json.loads(jcode_text)
            except json.JSONDecodeError:
                jcode_obj = {}
            reply: str = ""
            if isinstance(jcode_obj, dict):
                reply = jcode_obj.get("text") or jcode_obj.get("response") or jcode_obj.get("content") or ""
                if not reply and "choices" in jcode_obj:
                    choices = jcode_obj["choices"]
                    if isinstance(choices, list) and choices:
                        msg = choices[0].get("message", "") if isinstance(choices[0], dict) else ""
                        if isinstance(msg, dict):
                            reply = msg.get("content", "")
                        elif isinstance(msg, str):
                            reply = msg
            if reply:
                yield {"type": "text_delta", "text": reply}
            elif jcode_text:
                yield {"type": "text_delta", "text": jcode_text}


class _AnthropicAdapter(_BaseCLIAdapter):
    """SDK adapter stub for model discovery. No CLI binary involved."""
    name = "anthropic"
    default_timeout_s = 120

    def manages_own_auth(self) -> bool:
        return False

    def build_command(self, **kwargs) -> list[str]:
        raise NotImplementedError("anthropic is an SDK provider, not a CLI adapter")


class _OpenAIAdapter(_BaseCLIAdapter):
    """SDK adapter stub for model discovery. No CLI binary involved."""
    name = "openai"
    default_timeout_s = 120

    def manages_own_auth(self) -> bool:
        return False

    def build_command(self, **kwargs) -> list[str]:
        raise NotImplementedError("openai is an SDK provider, not a CLI adapter")


class _AntigravityAdapter(_BaseCLIAdapter):
    name = "antigravity"
    default_timeout_s = 3600

    def manages_own_auth(self) -> bool:
        return True

    def build_command(
        self,
        model: str,
        user_text: str,
        session_id: str,
        system_prompt: str,
        project_path: str | None = None,
    ) -> list[str]:
        agy_bin = shutil.which("agy") or shutil.which("antigravity") or "antigravity"
        body = user_text if user_text.lstrip().startswith("[") else f"[user]\n{user_text}"
        full_message = f"[system]\n{system_prompt}\n\n{body}"
        return [agy_bin, "--print", full_message, "--model", model]

    def normalize_event(self, line: str) -> list[dict[str, Any]]:
        """Plain-text output: every stdout line is one ``text_delta``.

        The line (including its trailing newline) is forwarded verbatim,
        matching the pre-refactor driver's chunk-to-text_delta mapping.
        """
        if line:
            return [{"type": "text_delta", "text": line}]
        return []


_ADAPTERS: dict[str, CLIAdapter] = {
    "anthropic": _AnthropicAdapter(),
    "openai": _OpenAIAdapter(),
    "opencode": _OpenCodeAdapter(),
    "jcode": _JCodeAdapter(),
    "antigravity": _AntigravityAdapter(),
}


def get_adapter(name: str) -> CLIAdapter:
    """Look up an adapter by name. Raises ``KeyError`` on unknown."""
    return _ADAPTERS[name]


def list_adapters() -> list[str]:
    """Return the names of all registered adapters (sorted)."""
    return sorted(_ADAPTERS.keys())
