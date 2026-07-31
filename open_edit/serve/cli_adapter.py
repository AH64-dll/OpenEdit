"""v1.7 — CLI adapter interface.

A ``CLIAdapter`` is a thin facade over a single CLI LLM backend
(``pi``, ``opencode``, ``antigravity``, ``jcode``). The interface is
deliberately minimal — every method exists because a real provider
difference required it (see the design spec, §3).

Adapters register themselves via ``_ADAPTERS`` and are looked up by
``get_adapter(name)``. This is a plain dict, not a factory or DI
container; adding a third CLI is one import + one entry.

Per-adapter event normalization (v1.9, task 5.3)
------------------------------------------------
The generic CLI driver feeds raw stdout lines to
``adapter.stream_events()`` (default: one line at a time through
``adapter.normalize_event(line)``).  Provider-specific output shapes
that used to be per-provider name branches in the driver now live
here:

- ``pi``          — JSON-lines; each line maps to 0..n events via the
                    shared ``_pi_normalize_event`` helper.
- ``opencode``    — JSON-lines; delegates to ``normalize_opencode_line``.
- ``antigravity`` — plain text; each line is one ``text_delta``.
- ``jcode``       — a single JSON blob on stdout (not line-streamed);
                    overrides ``stream_events`` to accumulate.

``defers_done`` — the pi adapter defers the terminal ``done`` to its
caller (the cost-extraction wrapper); the driver must not emit one.
``check_exit_status`` — pi surfaces non-zero exits via stderr; the
other adapters own their terminal semantics and early-returned before
the driver's exit check, so they keep that behaviour (no exit check).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from .opencode_adapter import normalize_opencode_line

if TYPE_CHECKING:
    from .llm.events import StreamEvent


@runtime_checkable
class CLIAdapter(Protocol):
    """One CLI backend. Stateless; methods only."""

    name: str
    default_timeout_s: int
    defers_done: bool
    check_exit_status: bool

    def default_model(self) -> str: ...
    def available_models(self) -> list[str]: ...
    def supports_tools(self) -> bool: ...
    def supports_images(self) -> bool: ...
    def manages_own_auth(self) -> bool: ...
    def extension_path(self) -> str | None: ...
    def build_command(
        self,
        model: str,
        user_text: str,
        session_id: str,
        extension_path: str | None,
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

    defers_done = False
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

    def extension_path(self) -> str | None:
        return None

    def normalize_event(self, line: str) -> list[dict[str, Any]]:
        return []

    async def stream_events(
        self,
        stdout: AsyncIterator[bytes],
    ) -> AsyncIterator[dict[str, Any]]:
        """Default: decode each stdout line and map it via ``normalize_event``.

        Lines are NOT stripped — adapters that care (pi, opencode) strip
        themselves; antigravity preserves the raw line (incl. newline)
        exactly as the pre-refactor driver yielded it.
        """
        async for raw in stdout:
            for ev in self.normalize_event(raw.decode("utf-8", errors="replace")):
                yield ev


# --- provider-specific helpers -----------------------------------------

def _pi_binary() -> str:
    return os.environ.get("OPEN_EDIT_PI_BINARY", "").strip() or shutil.which("pi") or "pi"


def _pi_extension_path() -> str:
    """Default: <open_edit>/serve/pi_extension/extension.ts"""
    explicit = os.environ.get("OPEN_EDIT_PI_EXTENSION", "").strip()
    if explicit:
        return explicit
    # This module is at <pkg>/open_edit/serve/cli_adapter.py; the
    # extension is at <pkg>/open_edit/serve/pi_extension/extension.ts
    here = Path(__file__).resolve()
    return str(here.parent / "pi_extension" / "extension.ts")


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

class _PiAdapter(_BaseCLIAdapter):
    name = "pi"
    default_timeout_s = 3600
    defers_done = True
    check_exit_status = True

    def manages_own_auth(self) -> bool:
        return True  # reads ~/.pi/agent/auth.json

    def extension_path(self) -> str | None:
        return _pi_extension_path()

    def build_command(
        self,
        model: str,
        user_text: str,
        session_id: str,
        extension_path: str | None,
        system_prompt: str,
        project_path: str | None = None,
    ) -> list[str]:
        # Resolve the pi binary the same way the legacy _pi_binary() did:
        # OPEN_EDIT_PI_BINARY env var (absolute path) wins; otherwise
        # fall back to PATH lookup; otherwise just "pi" (which will
        # surface a FileNotFoundError in _stream_cli if missing).
        pi_bin = _pi_binary()
        cmd = [
            pi_bin,
            "--provider", "opencode-go",
            "--model", model,
            "--mode", "json",
            "--no-extensions",
            "--print", user_text,
            "--append-system-prompt", system_prompt,
        ]
        cmd += ["--session-id", session_id]
        if extension_path:
            # Insert --extension after --no-extensions so the user's
            # extension wins over any default.
            cmd[cmd.index("--no-extensions") + 1:cmd.index("--no-extensions") + 1] = [
                "--extension", extension_path,
            ]
        return cmd

    def normalize_event(self, line: str) -> list[dict[str, Any]]:
        """Map one raw pi stdout line to 0..n StreamEvents.

        JSON-lines input: decode + parse, then run the shared
        ``_pi_normalize_event`` object normalizer. ``done`` events are
        suppressed here — the pi cost wrapper owns the terminal ``done``
        (it must come after the ``usage`` event).
        """
        line = line.strip()
        if not line:
            return []
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            return []
        if not isinstance(obj, dict):
            return []
        return [
            ev for ev in _normalize_pi_object(obj)
            if ev.get("type") != "done"
        ]


def _normalize_pi_object(obj: dict[str, Any]) -> list[dict[str, Any]]:
    """Map one parsed pi JSON event to one or more of our StreamEvent dicts.

    Pi's event types we care about:
    - ``message_update`` with ``assistantMessageEvent.type=text_delta`` and
      ``delta: "..."`` → emit a ``text_delta``.
    - ``message_end`` with ``role=assistant`` and ``content[*].type=toolCall``
      → emit a ``tool_use`` (accumulated; tool name + id + parsed args).
    - ``message_end`` with ``role=toolResult`` → emit a ``tool_result``
      with the tool's output (we do NOT re-execute the tool; the pi
      extension already ran it via the bridge).
    - ``turn_end`` → caller derives ``done`` from the absence of tool_use.
    - ``agent_end`` → already accounted for by the done emit.
    - ``error`` → emit ``error``.

    Tool inputs are emitted as already-parsed dicts (pi may emit the
    arguments as a JSON string; we parse defensively).
    """
    et = obj.get("type")
    if et == "message_update":
        ame = obj.get("assistantMessageEvent") or {}
        if ame.get("type") == "text_delta":
            delta = ame.get("delta") or ""
            if delta:
                return [{"type": "text_delta", "text": delta}]
        return []
    if et == "message_end":
        msg = obj.get("message") or {}
        role = msg.get("role")
        content = msg.get("content") or []
        if not isinstance(content, list):
            return []

        # toolResult message: pi has already run the tool (via the
        # extension), so we just forward the result to the agent loop.
        if role == "toolResult":
            tool_name = msg.get("toolName", "")
            tool_call_id = msg.get("toolCallId", "")
            is_error = bool(msg.get("isError"))
            # The result content is typically a list of {type:"text", text:"..."}
            # blocks; the first one is the JSON the bridge emitted.
            result_text = ""
            if content and isinstance(content[0], dict):
                result_text = content[0].get("text", "")
            # Parse the JSON if possible.
            try:
                parsed_result = json.loads(result_text) if result_text else {}
            except json.JSONDecodeError:
                parsed_result = {"raw": result_text}
            if is_error:
                err_msg = (
                    parsed_result.get("error", "unknown")
                    if isinstance(parsed_result, dict) else str(parsed_result)
                )
                return [{
                    "type": "tool_result",
                    "name": tool_name,
                    "result": parsed_result if isinstance(parsed_result, dict) else {"value": parsed_result},
                    "is_error": True,
                    "tool_use_id": tool_call_id,
                    "error_message": err_msg,
                }]
            return [{
                "type": "tool_result",
                "name": tool_name,
                "result": parsed_result,
                "tool_use_id": tool_call_id,
            }]

        if role != "assistant":
            return []

        # Surface provider-level errors (429 rate limits, auth failures,
        # model unavailability, etc.). Pi emits these as message_end
        # events with stopReason="error" and an errorMessage string —
        # but with an empty content array, so without this check the
        # error is silently swallowed and the user sees no response.
        if msg.get("stopReason") == "error" and msg.get("errorMessage"):
            err = msg["errorMessage"]
            # Try to extract a human-readable message from the JSON
            # error body that opencode-go returns (e.g. "429 {...}").
            try:
                # Strip the leading HTTP status code if present
                if err[:4].strip().isdigit():
                    err_json = json.loads(err.split(" ", 1)[1])
                    err = (
                        err_json.get("error", {}).get("message", "")
                        or err_json.get("message", "")
                        or err
                    )
            except (json.JSONDecodeError, IndexError, KeyError, TypeError):
                pass  # use the raw errorMessage string
            return [{"type": "error", "message": f"LLM provider error: {err}"}]

        out: list[dict[str, Any]] = []
        for blk in content:
            if not isinstance(blk, dict):
                continue
            btype = blk.get("type")
            if btype == "toolCall":
                raw_args = blk.get("arguments", {})
                if isinstance(raw_args, str):
                    try:
                        raw_args = json.loads(raw_args)
                    except json.JSONDecodeError:
                        raw_args = {"_raw": raw_args}
                out.append({
                    "type": "tool_use",
                    "id": blk.get("id", ""),
                    "name": blk.get("name", ""),
                    "input": raw_args if isinstance(raw_args, dict) else {"value": raw_args},
                })
            elif btype == "text":
                # Final text is also delivered via message_end; we
                # already streamed the deltas, so we skip here to avoid
                # duplicating the text in the UI.
                pass
        # If there was a toolCall, the assistant didn't return end_turn.
        # The agent loop sees a tool_use and continues; we DON'T emit
        # done here — the agent loop's logic handles stop_reason.
        return out
    if et == "error":
        return [{"type": "error", "message": str(obj.get("error", "pi error"))}]
    return []


def _pi_normalize_event(obj: dict[str, Any]) -> list[dict[str, Any]]:
    """Compat: normalize one parsed pi JSON object (dict → events).

    Kept as a module-level function so existing callers (and the pi
    event-mapping tests) don't need an adapter instance.  The
    ``_PiAdapter.normalize_event`` line parser delegates here.
    """
    return _normalize_pi_object(obj)


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
        extension_path: str | None,
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
        if extension_path:
            cmd.insert(cmd.index(full_message), "--extension")
            cmd.insert(cmd.index("--extension") + 1, extension_path)
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
        extension_path: str | None,
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
        extension_path: str | None,
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
    "pi": _PiAdapter(),
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
