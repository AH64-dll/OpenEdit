"""Public entry point: ``stream_chat`` (async generator) + CLI conversation
serialization helpers.

The dispatcher is provider-agnostic: every provider exposes a
``spec.stream(messages, tools, system, model, session_id=..., project_path=...)``
callable in ``providers.py`` (SDK streams take the 4 positional args; CLI
streams are name-bound closures that resolve their own adapter).  The only
transport-level distinction is SDK vs CLI, never a per-provider name.
"""
from __future__ import annotations

import asyncio
import json
import sys
import traceback
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from .events import StreamEvent
from .keys import _model, _provider, effective_provider


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_CLI_HISTORY_CHAR_BUDGET = 32_000


def _message_plain_text(message: dict[str, Any]) -> str:
    """Extract plain text from a chat message content field."""
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for blk in content:
            if isinstance(blk, dict) and blk.get("type") == "text":
                text = blk.get("text", "")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
            elif isinstance(blk, str) and blk.strip():
                parts.append(blk.strip())
        return "\n".join(parts)
    return ""


def _serialize_cli_conversation(
    messages: list[dict[str, Any]],
    *,
    char_budget: int = _CLI_HISTORY_CHAR_BUDGET,
) -> str:
    """Serialize role-separated turns for CLI adapters without sessions.

    Oldest turns are dropped first when the transcript exceeds
    ``char_budget``. Tool results are included as assistant-visible
    context so prior decisions are not silently discarded.
    """
    parts: list[str] = []
    for message in messages:
        role = message.get("role")
        if role == "system":
            continue
        text = _message_plain_text(message)
        if role == "tool":
            name = message.get("name") or message.get("tool_name") or "tool"
            if not text:
                result = message.get("content") or message.get("result")
                if result is not None and not isinstance(result, (str, list)):
                    text = json.dumps(result, ensure_ascii=False)[:2_000]
            if text:
                parts.append(f"[tool:{name}]\n{text}")
            continue
        if role not in ("user", "assistant") or not text:
            continue
        parts.append(f"[{role}]\n{text}")

    while parts and sum(len(p) + 2 for p in parts) > char_budget:
        parts.pop(0)
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def stream_chat(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    system: str,
    session_id: str | None = None,
    project_path: str | None = None,
) -> AsyncIterator[StreamEvent]:
    """Stream an LLM response as a sequence of :class:`StreamEvent`.

    ``messages`` is the standard Anthropic messages list. ``tools`` is the
    Anthropic tools spec (list of ``{"name", "description", "input_schema"}``
    dicts). ``system`` is the system prompt. ``session_id`` is used by the
    ``pi`` provider to maintain a persistent session across turns.
    ``project_path`` is used by the ``pi`` provider to tell the extension
    which project to operate on (via ``OPEN_EDIT_PROJECT`` env var).

    The function is an async generator — callers iterate it with
    ``async for event in stream_chat(...):``.

    Tool inputs are accumulated from ``input_json_delta`` events and only
    emitted once the block is closed (so callers receive one fully-formed
    ``tool_use`` event per tool call, not a stream of partial JSON).

    v1.7: when ``project_path`` is provided and contains a
    ``.open_edit/config.toml`` with an ``[llm]`` table, the per-project
    provider + model override the env vars (``OPEN_EDIT_LLM_PROVIDER``
    and ``OPEN_EDIT_LLM_MODEL``) for the duration of this call. This is
    what makes the provider+model selection bar in the chat UI
    functional: the PUT endpoint writes to the per-project config and
    the next chat turn picks up the change.

    Provider-level misconfiguration (missing API key, unknown provider,
    missing SDK) is caught here and surfaced as a single
    ``{"type": "error", "message": "..."}`` event so the user sees the
    real cause, not a wrapped ``RuntimeError`` or ``ModuleNotFoundError``.
    """
    # v1.7: per-project LLM config takes precedence over env vars when
    # ``project_path`` points at a directory with a readable
    # ``.open_edit/config.toml``. Any error (missing file, parse error,
    # unknown provider) silently falls back to the env defaults so a
    # broken project config never wedges the chat.
    project_provider: str | None = None
    project_model: str | None = None
    resolved = effective_provider(project_path)
    if resolved != _provider():
        project_provider = resolved
    if project_path is not None:
        try:
            proj_dir = Path(project_path)
        except (TypeError, ValueError):
            proj_dir = None  # type: ignore[assignment]
        if proj_dir is not None and (proj_dir / ".open_edit" / "config.toml").is_file():
            try:
                from ..llm_config import load_llm_config
                cfg = load_llm_config(proj_dir)
                project_model = cfg.model
            except Exception:
                pass  # fall back to env on any error (parse, validation, etc.)

    provider = project_provider or _provider()
    try:
        from ..providers import resolve_provider
        spec = resolve_provider(provider)
    except KeyError as exc:
        yield {"type": "error", "message": str(exc)}
        return

    model = project_model or _model()

    max_retries = 2
    for attempt in range(max_retries + 1):
        events_yielded = 0
        try:
            if spec.transport == "cli":
                # CLI streams are name-bound closures from providers.py;
                # the adapter (incl. the pi cost wrapper) is resolved there.
                async for ev in spec.stream(
                    messages, tools, system, model,
                    session_id=session_id, project_path=project_path,
                ):
                    events_yielded += 1
                    yield ev
            else:
                async for ev in spec.stream(
                    messages, tools, system, model,
                ):
                    events_yielded += 1
                    yield ev
            break
        except (ConnectionError, TimeoutError, OSError) as exc:
            if attempt < max_retries and events_yielded == 0:
                await asyncio.sleep(0.2 * (2 ** attempt))
                continue
            yield {"type": "error", "message": f"{spec.name} network error: {exc}"}
            return
        except RuntimeError as exc:
            yield {"type": "error", "message": str(exc)}
            return
        except ImportError as exc:
            msg = getattr(spec, "missing_error", None) or str(exc)
            yield {"type": "error", "message": msg}
            return
        except Exception as exc:
            exc_str = str(exc).lower()
            is_transient = (
                "connection" in exc_str or "timeout" in exc_str or "network" in exc_str or
                exc.__class__.__name__ in ("APIConnectionError", "NetworkError", "TimeoutException", "ConnectTimeout", "ReadTimeout")
            )
            if is_transient and attempt < max_retries and events_yielded == 0:
                await asyncio.sleep(0.2 * (2 ** attempt))
                continue

            # Catch-all: log to stderr so the dev sees the traceback, then
            # yield a single error event for the UI.
            traceback.print_exc(file=sys.stderr)
            yield {"type": "error", "message": f"{spec.name} provider error: {exc}"}
            return
