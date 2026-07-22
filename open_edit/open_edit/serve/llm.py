"""Async streaming LLM client for the Open Edit server.

Three backends supported via ``OPEN_EDIT_LLM_PROVIDER``:

- ``anthropic`` (default) — direct Anthropic SDK streaming.
- ``openai``              — direct OpenAI SDK streaming.
- ``pi``                  — spawn the ``pi`` CLI as a subprocess and parse
                            its JSON output. The pi process loads our
                            ``open_edit/serve/pi_extension/extension.ts``
                            which registers the 11 Open Edit tools.

Environment
-----------
``OPEN_EDIT_LLM_API_KEY``    — required for anthropic/openai.
``OPEN_EDIT_LLM_MODEL``      — model name (default ``claude-sonnet-4-5`` for
                                anthropic, ``gpt-4o`` for openai, ``minimax-m3``
                                for pi).
``OPEN_EDIT_LLM_PROVIDER``   — ``anthropic`` | ``openai`` | ``pi`` (default
                                ``anthropic``).
``OPEN_EDIT_LLM_MAX_TOKENS`` — per-turn cap (default 4096). Anthropic only.
``OPEN_EDIT_PI_BINARY``      — path to the ``pi`` binary (default: from PATH).
``OPEN_EDIT_PI_EXTENSION``   — path to the open_edit pi extension .ts file
                                (default: ``<pkg>/serve/pi_extension/extension.ts``).
``OPEN_EDIT_PI_PROVIDER``    — provider name passed to pi (default ``opencode-go``).
``OPEN_EDIT_PI_SESSION_ID``  — pi session id (set per-WS connection).
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
from collections.abc import AsyncIterator
from contextlib import suppress
from pathlib import Path
from typing import Any, Literal, TypedDict

from . import cost as cost_mod
from .cli_adapter import CLIAdapter, get_adapter
from .opencode_adapter import parse_opencode_events

# ``anthropic`` is listed as a hard dependency in pyproject.toml. We import
# lazily inside ``stream_chat`` so the module can still be imported in test
# environments that mock the SDK away.


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

class StreamEvent(TypedDict, total=False):
    """One event yielded by :func:`stream_chat`.

    Variants (the ``type`` field discriminates):
    - ``"text_delta"`` — assistant text delta. Carries ``text: str``.
    - ``"tool_use"``   — a tool invocation request. Carries ``id: str``,
      ``name: str``, ``input: dict``.
    - ``"tool_result"``— the result of a tool call. Carries ``name: str``,
      ``result: dict``. (Only emitted by the pi provider, which executes
      tools in its TS extension; other providers don't re-emit this.)
    - ``"usage"``      — token / cost accounting. Carries ``tokens: int``,
      ``cost_usd: float``, ``usage: dict``, ``source: str``.
    - ``"done"``       — terminal event. Carries ``stop_reason: str``.
    - ``"error"``      — misconfiguration or transport error. Carries
      ``message: str``.

    Total=False because each variant carries a different subset; the
    ``type`` field is the discriminant.
    """
    type: Literal[
        "text_delta", "tool_use", "tool_result",
        "usage", "done", "error",
    ]
    text: str
    id: str
    name: str
    input: dict
    result: dict
    tokens: int
    cost_usd: float
    usage: dict
    source: str
    stop_reason: str
    message: str


def _coerce_event(raw: dict[str, Any]) -> StreamEvent:
    if not isinstance(raw, dict) or "type" not in raw:
        raise ValueError("StreamEvent must contain a 'type' field")
    out = dict(raw)
    etype = out.get("type")
    if etype == "text_delta" and "text" not in out:
        out["text"] = ""
    elif etype == "tool_use":
        out.setdefault("id", "")
        out.setdefault("name", "")
        out.setdefault("input", {})
    elif etype == "tool_result":
        out.setdefault("name", "")
        out.setdefault("result", {})
    elif etype == "done" and "stop_reason" not in out:
        out["stop_reason"] = "end_turn"
    return out  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _api_key(provider: str | None = None) -> str:
    key = (
        os.environ.get("OPEN_EDIT_LLM_API_KEY", "").strip()
        or os.environ.get("OPENCODE_API_KEY", "").strip()
        or os.environ.get("ANTHROPIC_API_KEY", "").strip()
        or os.environ.get("OPENAI_API_KEY", "").strip()
    )
    if not key and provider:
        from .runtimes.keys_store import get_stored_key
        key = get_stored_key(provider) or ""
    if not key:
        from .runtimes.keys_store import get_stored_key
        key = (
            get_stored_key("anthropic")
            or get_stored_key("opencode")
            or get_stored_key("openai")
            or get_stored_key("antigravity")
            or ""
        )
    if not key:
        p_title = provider.lower() if provider else "llm"
        raise RuntimeError(
            f"{p_title} provider: OPEN_EDIT_LLM_API_KEY is not set. Set it or configure a key in Settings (⚙️)."
        )
    return key


def _model() -> str:
    return os.environ.get("OPEN_EDIT_LLM_MODEL", "claude-sonnet-4-5").strip()


def _provider() -> str:
    return os.environ.get("OPEN_EDIT_LLM_PROVIDER", "anthropic").strip().lower()


def _max_tokens() -> int:
    try:
        return int(os.environ.get("OPEN_EDIT_LLM_MAX_TOKENS", "4096"))
    except ValueError:
        return 4096


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
    if project_path is not None:
        try:
            proj_dir = Path(project_path)
        except (TypeError, ValueError):
            proj_dir = None  # type: ignore[assignment]
        if proj_dir is not None and (proj_dir / ".open_edit" / "config.toml").is_file():
            try:
                from .llm_config import load_llm_config
                cfg = load_llm_config(proj_dir)
                project_provider = cfg.provider
                project_model = cfg.model
            except Exception:
                pass  # fall back to env on any error (parse, validation, etc.)

    provider = project_provider or _provider()
    try:
        from .providers import resolve_provider
        spec = resolve_provider(provider)
    except KeyError as exc:
        yield {"type": "error", "message": str(exc)}
        return

    model = project_model or _model()

    max_retries = 2
    for attempt in range(max_retries + 1):
        events_yielded = 0
        try:
            if spec.name == "pi":
                async for ev in _stream_pi(messages, tools, system, session_id, project_path, model):
                    events_yielded += 1
                    yield ev
            elif spec.is_cli:
                from .cli_adapter import get_adapter
                adapter = get_adapter(spec.name)
                async for ev in _stream_cli(
                    adapter, model, messages, tools, system,
                    session_id, project_path,
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
            import sys
            import traceback
            traceback.print_exc(file=sys.stderr)
            yield {"type": "error", "message": f"{spec.name} provider error: {exc}"}
            return


# ---------------------------------------------------------------------------
# Pi implementation
# ---------------------------------------------------------------------------

def _pi_binary() -> str:
    return os.environ.get("OPEN_EDIT_PI_BINARY", "").strip() or shutil.which("pi") or "pi"


def _pi_extension_path() -> str:
    """Default: <open_edit>/serve/pi_extension/extension.ts"""
    explicit = os.environ.get("OPEN_EDIT_PI_EXTENSION", "").strip()
    if explicit:
        return explicit
    # llm.py is at <pkg>/open_edit/serve/llm.py; extension is at
    # <pkg>/open_edit/serve/pi_extension/extension.ts
    here = Path(__file__).resolve()
    return str(here.parent / "pi_extension" / "extension.ts")


def _pi_provider_name() -> str:
    return os.environ.get("OPEN_EDIT_PI_PROVIDER", "opencode-go").strip()


def _pi_model() -> str:
    return os.environ.get("OPEN_EDIT_LLM_MODEL", "minimax-m3").strip()


async def _stream_pi(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    system: str,
    session_id: str | None,
    project_path: str | None = None,
    model: str | None = None,
) -> AsyncIterator[StreamEvent]:
    """Pi provider — delegates to _stream_cli with the PiAdapter.

    After _stream_cli finishes, we read the pi session JSONL delta to
    extract the per-call cost (v1.4 P1-3). The opencode provider does
    not need this — it reports cost directly in step_finish events.

    Event order: text_deltas → tool_use → tool_result → ``usage`` →
    ``done``. _stream_cli deliberately does NOT emit a trailing
    ``done`` for the pi branch — the cost-extraction-and-done
    responsibility is owned by this wrapper, so the agent loop sees
    a single ``done`` at the very end, after the ``usage`` event.
    """
    sid = session_id or f"oe-{os.getpid()}"
    sessions_dir = cost_mod.default_pi_sessions_dir()
    session_path = cost_mod.find_pi_session_file(sid, sessions_dir)
    baseline_size = session_path.stat().st_size if session_path is not None else 0

    adapter = get_adapter("pi")
    async for ev in _stream_cli(
        adapter, model or _model(), messages, tools, system, session_id, project_path,
    ):
        yield ev

    # Cost extraction (v1.4 P1-3). _stream_cli did NOT emit a trailing
    # ``done`` for the pi branch — we own it here so the final order is
    # usage → done. Pi cost is read from the session JSONL delta.
    if session_path is None:
        session_path = cost_mod.find_pi_session_file(sid, sessions_dir)
    if session_path is None or not session_path.exists():
        yield {
            "type": "usage", "source": "unavailable",
            "tokens": 0, "cost_usd": 0.0, "usage": {},
        }
    else:
        delta = cost_mod.parse_pi_session_usage_delta(session_path, last_size=baseline_size)
        yield {
            "type": "usage", "source": "pi",
            "tokens": delta["tokens"], "cost_usd": delta["cost_usd"], "usage": {},
        }

    yield {"type": "done", "stop_reason": "end_turn"}


def _pi_normalize_event(obj: dict[str, Any]) -> list[StreamEvent]:
    """Map one pi JSON event to one or more of our StreamEvent dicts.

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

        out: list[StreamEvent] = []
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


async def _stream_cli(
    adapter: CLIAdapter,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    system: str,
    session_id: str | None,
    project_path: str | None,
) -> AsyncIterator[StreamEvent]:
    """Generic subprocess driver for any CLIAdapter (pi, opencode).

    Pulls the last user message text from ``messages``, builds the
    command via ``adapter.build_command``, spawns the subprocess, and
    yields ``StreamEvent``-shaped dicts.

    Enforces ``adapter.default_timeout_s`` on the subprocess lifetime
    (R4 fix). On timeout, kills the process, yields an ``error`` event
    with a clear message, then a ``done`` event with stop_reason=error.
    """
    user_text = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            content = m.get("content")
            if isinstance(content, str):
                user_text = content
            elif isinstance(content, list):
                for blk in content:
                    if isinstance(blk, dict) and blk.get("type") == "text":
                        user_text = blk.get("text", "")
                        break
            break
    if not user_text:
        yield {"type": "error", "message": f"{adapter.name} provider: no user message found"}
        yield {"type": "done", "stop_reason": "error"}
        return

    sid = session_id or f"oe-{os.getpid()}"
    # Pi-specific extension path: the opencode adapter doesn't use it.
    extension_path: str | None = None
    # Track which adapter we're driving so we know whether to emit the
    # trailing "done" at the bottom of this function. For pi, the
    # _stream_pi wrapper owns the final done (it must come AFTER the
    # cost-extraction "usage" event). For opencode, the normalizer's
    # own step_finish → done is authoritative and we return early above
    # (but the ``not is_pi`` guard below is a defensive belt).
    is_pi = adapter.name == "pi"
    if is_pi:
        extension_path = _pi_extension_path()

    cmd = adapter.build_command(
        model=model,
        user_text=user_text,
        session_id=sid,
        extension_path=extension_path,
        system_prompt=system,
    )

    env = dict(os.environ)
    pkg_root = str(Path(__file__).resolve().parents[2])
    env["PYTHONPATH"] = (
        pkg_root + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    )
    if project_path:
        env["OPEN_EDIT_PROJECT"] = str(project_path)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env,
        )
    except FileNotFoundError as exc:
        yield {"type": "error", "message": f"{adapter.name} binary not found: {exc}"}
        yield {"type": "done", "stop_reason": "error"}
        return

    async def _read_with_timeout() -> AsyncIterator[bytes]:
        assert proc.stdout is not None
        while True:
            try:
                line = await asyncio.wait_for(proc.stdout.readline(), timeout=adapter.default_timeout_s)
            except TimeoutError:
                with suppress(ProcessLookupError):
                    proc.kill()
                raise
            if not line:
                return
            yield line

    saw_text = False
    try:
        if adapter.name == "pi":
            # Read JSON-line events and run them through the existing
            # pi normalizer. We suppress the inner "done" event so the
            # final done can be emitted at the end (after the cost
            # extraction in _stream_pi, which appends a "usage" event).
            buf = b""
            async for chunk in _read_with_timeout():
                buf += chunk
                while b"\n" in buf:
                    raw_line, buf = buf.split(b"\n", 1)
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    for ev in _pi_normalize_event(obj):
                        if ev.get("type") == "done":
                            # Defer; final done is emitted at the end.
                            continue
                        if ev.get("type") == "text_delta":
                            saw_text = True
                        yield ev
        elif adapter.name == "jcode":
            # JCode ``--json`` outputs a single JSON blob (not streaming).
            # Read all stdout, parse and extract the assistant reply.
            jcode_raw = b""
            async for chunk in _read_with_timeout():
                jcode_raw += chunk
            jcode_text = jcode_raw.decode("utf-8", errors="replace").strip()
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
                    saw_text = True
                    yield {"type": "text_delta", "text": reply}
                elif jcode_text:
                    saw_text = True
                    yield {"type": "text_delta", "text": jcode_text}
            yield {"type": "done", "stop_reason": "end_turn"}
            return
        elif adapter.name == "antigravity":
            async for chunk in _read_with_timeout():
                text = chunk.decode("utf-8", errors="replace")
                if text:
                    saw_text = True
                    yield {"type": "text_delta", "text": text}
            yield {"type": "done", "stop_reason": "end_turn"}
            return
        elif adapter.name == "opencode":
            # opencode normalizer is already adapter-aware; pass it the
            # raw byte stream and let it handle framing.
            async for ev in parse_opencode_events(_read_with_timeout()):
                if ev.get("type") == "text_delta":
                    saw_text = True
                yield ev
            return
        else:
            # Fallback for any other CLI adapter: stream stdout lines as text_delta
            async for chunk in _read_with_timeout():
                text = chunk.decode("utf-8", errors="replace")
                if text:
                    saw_text = True
                    yield {"type": "text_delta", "text": text}
            yield {"type": "done", "stop_reason": "end_turn"}
            return
    except TimeoutError:
        with suppress(ProcessLookupError):
            proc.kill()
        yield {
            "type": "error",
            "message": f"{adapter.name} timeout: timed out after {adapter.default_timeout_s}s",
        }
        yield {"type": "done", "stop_reason": "error"}
        return
    except asyncio.CancelledError:
        with suppress(Exception):
            proc.kill()
        raise

    try:
        await asyncio.wait_for(proc.wait(), timeout=5.0)
    except TimeoutError:
        proc.kill()

    if proc.returncode != 0 and not saw_text:
        stderr_data = b""
        if proc.stderr is not None:
            with suppress(Exception):
                stderr_data = await proc.stderr.read()
        stderr_text = stderr_data.decode("utf-8", errors="replace").strip()
        yield {
            "type": "error",
            "message": stderr_text or f"{adapter.name} exited {proc.returncode}",
        }
        yield {"type": "done", "stop_reason": "error"}
        return

    # For the pi branch: do NOT emit a trailing "done" here. The
    # _stream_pi wrapper owns the final done — it must come AFTER the
    # cost-extraction "usage" event so the agent loop sees the order
    # text_deltas → tool_use → tool_result → usage → done. For the
    # opencode branch: the opencode normalizer already emitted "done"
    # inside its async-for loop above (and that branch returns early);
    # the ``not is_pi`` guard is defensive.
    if not is_pi:
        yield {"type": "done", "stop_reason": "end_turn"}


# ---------------------------------------------------------------------------
# Anthropic implementation
# ---------------------------------------------------------------------------

async def _stream_anthropic(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    system: str,
    model: str | None = None,
) -> AsyncIterator[StreamEvent]:
    # Check the API key before attempting the import so that a missing key
    # raises a clean RuntimeError (caught by the caller) rather than being
    # shadowed by an ImportError when the anthropic package is absent.
    api_key = _api_key("anthropic")
    import anthropic  # type: ignore

    client = anthropic.AsyncAnthropic(api_key=api_key)

    # Anthropic SDK streaming event names are stable across versions.
    async with client.messages.stream(
        model=model or _model(),
        max_tokens=_max_tokens(),
        system=system,
        messages=messages,
        tools=tools or anthropic.NOT_GIVEN,  # type: ignore[attr-defined]
    ) as stream:
        # We accumulate tool_use blocks manually because the high-level
        # ``stream.text()`` helper doesn't surface tool calls cleanly.
        current_tool: dict[str, Any] | None = None
        current_tool_input_json = ""

        async for event in stream:
            etype = event.type

            if etype == "content_block_start":
                block = event.content_block
                if getattr(block, "type", None) == "tool_use":
                    current_tool = {
                        "id": block.id,
                        "name": block.name,
                    }
                    current_tool_input_json = ""

            elif etype == "content_block_delta":
                delta = event.delta
                dtype = getattr(delta, "type", None)
                if dtype == "text_delta":
                    text = getattr(delta, "text", "")
                    if text:
                        yield {"type": "text_delta", "text": text}
                elif dtype == "input_json_delta":
                    partial = getattr(delta, "partial_json", "")
                    if partial:
                        current_tool_input_json += partial

            elif etype == "content_block_stop":
                if current_tool is not None:
                    parsed_input: dict[str, Any] = {}
                    raw = current_tool_input_json.strip()
                    if raw:
                        try:
                            parsed = json.loads(raw)
                            parsed_input = parsed if isinstance(parsed, dict) else {"value": parsed}
                        except json.JSONDecodeError:
                            # Forward the raw string so the agent loop can
                            # surface a useful error rather than crash.
                            parsed_input = {"_raw": raw}
                    yield {
                        "type": "tool_use",
                        "id": current_tool["id"],
                        "name": current_tool["name"],
                        "input": parsed_input,
                    }
                    current_tool = None
                    current_tool_input_json = ""

            elif etype == "message_stop":
                final = await stream.get_final_message()
                # v1.4 P1-3: emit a ``usage`` event so the agent
                # loop can compute and surface per-turn cost. We
                # compute the cost here from the SDK's usage
                # object + the pricing config; the agent loop
                # aggregates across the turn.
                usage_obj = getattr(final, "usage", None)
                if usage_obj is not None:
                    usage_dict = {
                        "input_tokens": int(getattr(usage_obj, "input_tokens", 0) or 0),
                        "output_tokens": int(getattr(usage_obj, "output_tokens", 0) or 0),
                        "cache_creation_input_tokens": int(
                            getattr(usage_obj, "cache_creation_input_tokens", 0) or 0
                        ),
                        "cache_read_input_tokens": int(
                            getattr(usage_obj, "cache_read_input_tokens", 0) or 0
                        ),
                    }
                    cost_result = cost_mod.compute_anthropic_cost(
                        usage_dict, model or _model(),
                    )
                    if cost_result is None:
                        yield {
                            "type": "usage",
                            "source": "unavailable",
                            "tokens": sum(usage_dict.values()),
                            "cost_usd": 0.0,
                            "usage": usage_dict,
                        }
                    else:
                        tokens, cost_usd = cost_result
                        yield {
                            "type": "usage",
                            "source": "computed",
                            "tokens": tokens,
                            "cost_usd": cost_usd,
                            "usage": usage_dict,
                        }
                yield {
                    "type": "done",
                    "stop_reason": final.stop_reason or "end_turn",
                }


# ---------------------------------------------------------------------------
# OpenAI implementation (optional; minimal but functional)
# ---------------------------------------------------------------------------

async def _stream_openai(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    system: str,
    model: str | None = None,
) -> AsyncIterator[StreamEvent]:
    """OpenAI-compatible streaming.

    Converts the Anthropic-style ``tools`` spec to OpenAI's function-calling
    format on the fly. Only the subset of features Open Edit uses is
    implemented.
    """
    import openai  # type: ignore

    client = openai.AsyncOpenAI(api_key=_api_key("openai"))

    # Convert messages: Anthropic blocks -> OpenAI role/content
    oai_messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")
        if isinstance(content, str):
            oai_messages.append({"role": role, "content": content})
        elif isinstance(content, list):
            # Anthropic blocks -> OpenAI parts
            parts: list[dict[str, Any]] = []
            for block in content:
                btype = block.get("type")
                if btype == "text":
                    parts.append({"type": "text", "text": block.get("text", "")})
                elif btype == "tool_use":
                    parts.append({
                        "type": "function",
                        "id": block.get("id"),
                        "function": {
                            "name": block.get("name"),
                            "arguments": json.dumps(block.get("input", {})),
                        },
                    })
                elif btype == "tool_result":
                    parts.append({
                        "role": "tool",
                        "tool_call_id": block.get("tool_use_id"),
                        "content": json.dumps(block.get("content", "")),
                    })
            oai_messages.append({"role": role, "content": parts})

    # Convert tool specs: Anthropic -> OpenAI
    oai_tools = [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            },
        }
        for t in tools
    ]

    stream = await client.chat.completions.create(
        model=model or _model(),
        messages=oai_messages,
        tools=oai_tools or None,
        stream=True,
    )

    # Accumulate tool calls by index, emit each when the tool_call finishes.
    pending_tools: dict[int, dict[str, Any]] = {}
    finish_reason = "stop"
    # v1.4 P1-3: the OpenAI SDK only carries the usage object on
    # the LAST chunk (with finish_reason set). We capture the
    # latest usage we see, then emit it as a ``usage`` event after
    # the loop.
    last_usage: Any = None

    async for chunk in stream:
        if not chunk.choices:
            continue
        choice = chunk.choices[0]
        delta = choice.delta
        if delta.content:
            yield {"type": "text_delta", "text": delta.content}
        if delta.tool_calls:
            for call in delta.tool_calls:
                idx = call.index
                if idx not in pending_tools:
                    pending_tools[idx] = {
                        "id": call.id or "",
                        "name": (call.function.name if call.function else "") or "",
                        "args_json": "",
                    }
                else:
                    if call.id:
                        pending_tools[idx]["id"] = call.id
                    if call.function and call.function.name:
                        pending_tools[idx]["name"] = call.function.name
                if call.function and call.function.arguments:
                    pending_tools[idx]["args_json"] += call.function.arguments
        if choice.finish_reason:
            finish_reason = choice.finish_reason
        # The usage object lives at chunk.usage, not on the choice.
        chunk_usage = getattr(chunk, "usage", None)
        if chunk_usage is not None:
            last_usage = chunk_usage

    # Emit accumulated tool calls
    for idx in sorted(pending_tools.keys()):
        tool = pending_tools[idx]
        try:
            parsed = json.loads(tool["args_json"] or "{}")
        except json.JSONDecodeError:
            parsed = {"_raw": tool["args_json"]}
        yield {
            "type": "tool_use",
            "id": tool["id"],
            "name": tool["name"],
            "input": parsed,
        }

    # v1.4 P1-3: emit a ``usage`` event if the SDK gave us usage
    # data. The cost math happens here (against pricing.json) so
    # the agent loop can just aggregate per-call costs.
    if last_usage is not None:
        usage_dict = {
            "prompt_tokens": int(getattr(last_usage, "prompt_tokens", 0) or 0),
            "completion_tokens": int(getattr(last_usage, "completion_tokens", 0) or 0),
        }
        details = getattr(last_usage, "prompt_tokens_details", None)
        if details is not None:
            usage_dict["prompt_tokens_details"] = {
                "cached_tokens": int(getattr(details, "cached_tokens", 0) or 0),
            }
        cost_result = cost_mod.compute_openai_cost(usage_dict, model or _model())
        if cost_result is None:
            yield {
                "type": "usage",
                "source": "unavailable",
                "tokens": sum(v for k, v in usage_dict.items() if isinstance(v, int)),
                "cost_usd": 0.0,
                "usage": usage_dict,
            }
        else:
            tokens, cost_usd = cost_result
            yield {
                "type": "usage",
                "source": "computed",
                "tokens": tokens,
                "cost_usd": cost_usd,
                "usage": usage_dict,
            }

    # Map OpenAI finish_reason -> Anthropic-style stop_reason
    stop_map = {
        "stop": "end_turn",
        "tool_calls": "tool_use",
        "length": "max_tokens",
        "function_call": "tool_use",
    }
    yield {"type": "done", "stop_reason": stop_map.get(finish_reason, "end_turn")}
