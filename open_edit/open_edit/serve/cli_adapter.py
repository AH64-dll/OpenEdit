"""v1.7 — CLI adapter interface.

A ``CLIAdapter`` is a thin facade over a single CLI LLM backend
(currently ``pi`` and ``opencode``). The interface is deliberately
minimal — every method exists because a real provider difference
required it (see the design spec, §3).

The two adapters register themselves via ``_ADAPTERS`` and are looked
up by ``get_adapter(name)``. This is a plain dict, not a factory or
DI container; adding a third CLI is one import + one entry.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from typing import Protocol, runtime_checkable


# A lightweight copy of the StreamEvent TypedDict shape from llm.py.
# We don't import llm.py here to avoid a cycle (llm.py imports adapters).
class _StreamEvent(dict):
    """Marker subclass; consumers treat as dict[str, Any]."""


@runtime_checkable
class CLIAdapter(Protocol):
    """One CLI backend. Stateless; methods only."""

    name: str
    default_timeout_s: int

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
        extension_path: str | None,
        system_prompt: str,
    ) -> list[str]: ...


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

class _PiAdapter:
    name = "pi"
    default_timeout_s = 60

    def default_model(self) -> str:
        return "minimax-m3"

    def available_models(self) -> list[str]:
        # Hand-curated; pi has no clean introspection.
        return [
            "minimax-m3",
            "minimax-m2.7",
            "deepseek-v4-flash",
            "deepseek-v4-pro",
        ]

    def supports_tools(self) -> bool:
        return True

    def supports_images(self) -> bool:
        return True

    def manages_own_auth(self) -> bool:
        return True  # reads ~/.pi/agent/auth.json

    def build_command(
        self,
        model: str,
        user_text: str,
        session_id: str,
        extension_path: str | None,
        system_prompt: str,
    ) -> list[str]:
        # Resolve the pi binary the same way the legacy _pi_binary() did:
        # OPEN_EDIT_PI_BINARY env var (absolute path) wins; otherwise
        # fall back to PATH lookup; otherwise just "pi" (which will
        # surface a FileNotFoundError in _stream_cli if missing).
        pi_bin = os.environ.get("OPEN_EDIT_PI_BINARY", "").strip() or shutil.which("pi") or "pi"
        cmd = [
            pi_bin,
            "--provider", "opencode-go",
            "--model", model,
            "--mode", "json",
            "--no-extensions",
            "--session-id", session_id,
            "--print", user_text,
            "--append-system-prompt", system_prompt,
        ]
        if extension_path:
            # Insert --extension after --no-extensions so the user's
            # extension wins over any default.
            cmd[cmd.index("--no-extensions") + 1:cmd.index("--no-extensions") + 1] = [
                "--extension", extension_path,
            ]
        return cmd


class _OpenCodeAdapter:
    name = "opencode"
    default_timeout_s = 120

    def default_model(self) -> str:
        return "opencode-go/minimax-m3"

    def available_models(self) -> list[str]:
        return _opencode_models_via_cli()

    def supports_tools(self) -> bool:
        return False  # v1.7: no opencode-side extension yet

    def supports_images(self) -> bool:
        return False  # v1.7: chat mode only

    def manages_own_auth(self) -> bool:
        return True  # reads ~/.local/share/opencode/auth.json

    def build_command(
        self,
        model: str,
        user_text: str,
        session_id: str,
        extension_path: str | None,
        system_prompt: str,
    ) -> list[str]:
        # opencode has no --append-system-prompt flag; we prepend the
        # system prompt to the user message so the model still sees it.
        # The leading "[system]\n...\n\n[user]\n..." format keeps the
        # boundary unambiguous for the model.
        full_message = f"[system]\n{system_prompt}\n\n[user]\n{user_text}"
        cmd = [
            "opencode",
            "run",
            "--format", "json",
            "--model", model,
            "-s", session_id,
            "--title", f"oe-{session_id}",
            full_message,
        ]
        if extension_path:
            cmd.insert(cmd.index(full_message), "--extension")
            cmd.insert(cmd.index("--extension") + 1, extension_path)
        return cmd


_ADAPTERS: dict[str, CLIAdapter] = {
    "pi": _PiAdapter(),
    "opencode": _OpenCodeAdapter(),
}


def get_adapter(name: str) -> CLIAdapter:
    """Look up an adapter by name. Raises ``KeyError`` on unknown."""
    return _ADAPTERS[name]


def list_adapters() -> list[str]:
    """Return the names of all registered adapters (sorted)."""
    return sorted(_ADAPTERS.keys())
