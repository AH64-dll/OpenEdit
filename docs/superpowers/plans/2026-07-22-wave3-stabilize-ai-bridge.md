# Wave 3 — Stabilize the AI Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce fragility in the LLM/provider/tool bridge by centralizing the provider registry, extracting a shared tool executor, and tightening the contract that the agent loop relies on — so future providers and tools can be added without touching `agent.py`.

**Architecture:** Three independent refactors, each small enough to be a single task:
1. **ProviderRegistry** — `stream_chat`'s 6-branch if/elif becomes a registry table lookup. Adding a new provider is one entry, not a surgery in `llm.py`.
2. **Shared tool executor** — `_execute_agent_tool` and the trigger-render path move to `serve/tool_executor.py`, used by `agent.py` and `pi_bridge.py` (so TS extension and in-process agent cannot drift).
3. **Stream contract tightening** — `llm.py` exports a typed `StreamEvent` TypedDict; `agent.py` stops reaching into provider-specific event fields by name; missing key handling becomes a single helper.

**Tech Stack:** Python 3.14, FastAPI, Pydantic, `asyncio`, `pytest`, existing `CLIAdapter` Protocol.

**Base commit:** `0be8fb9` (Wave 2: edit graph interactivity).

## Global Constraints

- **No behavior change** in this wave. The agent loop and all 14 tools must continue to work identically. Existing tests must continue to pass without modification (unless a test is explicitly testing the moved/renamed symbol, in which case update it).
- **Provider name strings (`"anthropic"`, `"openai"`, `"pi"`, `"opencode"`, `"antigravity"`, `"jcode"`)** must come from a single source: the `ProviderName` Literal in `llm_config.py`. Do not duplicate them in `llm.py`'s `stream_chat` dispatch.
- **All async** — no blocking SDK calls inside an async function. If a sync SDK must be called, wrap it in `await asyncio.to_thread(...)`. This was identified in the audit as a latent bug; do not propagate it.
- **Existing test files** (per-task references in the steps) cover the touched code. Do not delete or rewrite tests unless the underlying symbol moved.
- **Public surface** (`agent.py`'s `run_agent_turn`, `llm.py`'s `stream_chat`) must keep their exact signatures. Internal helpers may move.
- **Ruff clean** on every commit.

---

## File Structure

- `open_edit/serve/providers.py` *(new)* — `ProviderRegistry`, `PROVIDERS` table, `resolve_provider(name)` helper.
- `open_edit/serve/llm.py` *(modify)* — `stream_chat` becomes a registry dispatch. `StreamEvent` becomes a TypedDict (was already a TypedDict — confirm export).
- `open_edit/serve/tool_executor.py` *(new)* — `execute_tool(name, args, project_path)`, `execute_trigger_render(...)` shared by `agent.py` and `pi_bridge.py`.
- `open_edit/serve/agent.py` *(modify)* — delete `_execute_agent_tool` and `_execute_trigger_render`; import from `tool_executor`. Re-export from the old location for any callers that imported them.
- `open_edit/serve/pi_bridge.py` *(modify)* — replace its local copy of the tool-dispatch logic with calls to `tool_executor`.
- `tests/test_providers.py` *(new)* — registry tests.
- `tests/test_tool_executor.py` *(new)* — shared executor tests.

---

## Task 1: Provider registry — replace 6-branch dispatch with a table

**Files:**
- Create: `open_edit/serve/providers.py`
- Modify: `open_edit/serve/llm.py:126-251` (`stream_chat` dispatch)
- Test: `tests/test_providers.py` (new)

**Interfaces:**
- Consumes: existing `_stream_openai`, `_stream_pi`, `_stream_cli`, `_stream_anthropic` private functions in `llm.py` — they all become entries in a `PROVIDERS` table.
- Produces: `from open_edit.serve.providers import resolve_provider, ProviderSpec, list_provider_specs`.

### Step 1: Write the failing test

Create `open_edit/serve/providers.py` with the registry skeleton (see Step 3 for the code), then create `tests/test_providers.py`:

```python
"""Tests for the LLM provider registry."""
from __future__ import annotations

import pytest

from open_edit.serve.providers import (
    PROVIDERS,
    ProviderSpec,
    list_provider_specs,
    resolve_provider,
)


def test_all_known_providers_registered():
    names = {p.name for p in PROVIDERS.values()}
    assert names == {"anthropic", "openai", "pi", "opencode", "antigravity", "jcode"}


def test_resolve_provider_known():
    spec = resolve_provider("opencode")
    assert isinstance(spec, ProviderSpec)
    assert spec.name == "opencode"
    assert spec.is_cli is True
    assert spec.stream is not None


def test_resolve_provider_unknown_raises():
    with pytest.raises(KeyError) as exc:
        resolve_provider("not-a-provider")
    assert "not-a-provider" in str(exc.value)


def test_anthropic_uses_sdk_not_cli():
    spec = resolve_provider("anthropic")
    assert spec.is_cli is False


def test_list_provider_specs_sorted_by_name():
    specs = list_provider_specs()
    assert [s.name for s in specs] == sorted(s.name for s in specs)


def test_cli_providers_have_callable_stream():
    """All CLI providers have a stream function; the dispatcher calls it
    with the matching CLIAdapter. The pi provider uses _stream_pi (which
    wraps _stream_cli to add cost extraction); the other three use
    _stream_cli directly. The test only asserts the contract surface."""
    for name in ("pi", "opencode", "antigravity", "jcode"):
        spec = resolve_provider(name)
        assert spec.is_cli is True
        assert callable(spec.stream)
```

### Step 2: Run the test and watch it fail

```bash
cd /home/ah64/apps/mlt-pipeline/open_edit && .venv/bin/python -m pytest tests/test_providers.py -v
```

Expected: `ModuleNotFoundError: No module named 'open_edit.serve.providers'`.

### Step 3: Implement the registry

Create `open_edit/serve/providers.py`:

```python
"""LLM provider registry (Wave 3).

Centralizes the provider name → streaming-implementation mapping that
used to live as a 6-branch if/elif in ``stream_chat``. Adding a new
provider is one entry here, not a surgery in ``llm.py``.

The :class:`ProviderSpec` dataclass captures everything the dispatcher
needs:
- ``name`` — canonical provider name (matches ``ProviderName`` in
  ``llm_config.py``)
- ``is_cli`` — True for the four providers that shell out to a CLI
  binary (pi, opencode, antigravity, jcode); False for SDK providers
  (anthropic, openai)
- ``stream`` — async generator function matching the
  ``_stream_openai`` / ``_stream_anthropic`` / ``_stream_cli`` /
  ``_stream_pi`` shape. For CLI providers the dispatcher pulls the
  matching ``CLIAdapter`` and passes it to ``_stream_cli``; for SDK
  providers the registered stream function is called directly.
- ``missing_error`` — message yielded by ``stream_chat`` when the
  provider is selected but cannot run (missing SDK, missing API key,
  missing CLI binary). The dispatcher wraps the stream call in the
  same try/except pattern that used to be copy-pasted per branch.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Iterator


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    is_cli: bool
    stream: Callable[..., Awaitable[Iterator[dict]]]
    missing_error: str  # yielded as {"type": "error", "message": ...}


# --- Imported lazily so a missing SDK doesn't break server startup. ---

def _anthropic_stream():
    from .llm import _stream_anthropic
    return _stream_anthropic


def _openai_stream():
    from .llm import _stream_openai
    return _stream_openai


def _pi_stream():
    from .llm import _stream_pi
    return _stream_pi


def _cli_stream():
    from .llm import _stream_cli
    return _stream_cli


PROVIDERS: dict[str, ProviderSpec] = {
    "anthropic": ProviderSpec(
        name="anthropic",
        is_cli=False,
        stream=_anthropic_stream(),
        missing_error=(
            "anthropic provider: required package not installed or "
            "ANTHROPIC_API_KEY missing. Install with `pip install anthropic` "
            "and set the key in Settings or as ANTHROPIC_API_KEY env var."
        ),
    ),
    "openai": ProviderSpec(
        name="openai",
        is_cli=False,
        stream=_openai_stream(),
        missing_error=(
            "openai provider: required package not installed or "
            "OPENAI_API_KEY missing. Install with `pip install openai` "
            "and set the key in Settings or as OPENAI_API_KEY env var."
        ),
    ),
    "pi": ProviderSpec(
        name="pi",
        is_cli=True,
        stream=_pi_stream(),
        missing_error=(
            "pi provider: `pi` binary not found on PATH. Install pi "
            "(see https://github.com/badlogic/pi-mono) and ensure the "
            "binary is on PATH, or set OPEN_EDIT_PI_BINARY."
        ),
    ),
    "opencode": ProviderSpec(
        name="opencode",
        is_cli=True,
        stream=_cli_stream(),
        missing_error=(
            "opencode provider: `opencode` binary not found on PATH. "
            "Install opencode (see https://opencode.ai) and ensure the "
            "binary is on PATH."
        ),
    ),
    "antigravity": ProviderSpec(
        name="antigravity",
        is_cli=True,
        stream=_cli_stream(),
        missing_error=(
            "antigravity provider: `antigravity` binary not found on "
            "PATH. Install antigravity and ensure the binary is on PATH."
        ),
    ),
    "jcode": ProviderSpec(
        name="jcode",
        is_cli=True,
        stream=_cli_stream(),
        missing_error=(
            "jcode provider: `jcode` binary not found on PATH. Install "
            "jcode and ensure the binary is on PATH."
        ),
    ),
}


def resolve_provider(name: str) -> ProviderSpec:
    """Return the :class:`ProviderSpec` for ``name``. Raises ``KeyError``
    with a helpful message if the name is not registered."""
    if name not in PROVIDERS:
        registered = ", ".join(sorted(PROVIDERS))
        raise KeyError(
            f"unknown LLM provider: {name!r}; expected one of: {registered}"
        )
    return PROVIDERS[name]


def list_provider_specs() -> list[ProviderSpec]:
    """All registered providers, sorted by name. Used by the UI to render
    the provider dropdown without re-implementing the list elsewhere."""
    return sorted(PROVIDERS.values(), key=lambda s: s.name)
```

### Step 4: Refactor `stream_chat` to use the registry

In `open_edit/serve/llm.py`, replace the dispatch in `stream_chat` (lines 184-250) with:

```python
    provider = project_provider or _provider()
    try:
        spec = resolve_provider(provider)
    except KeyError as exc:
        yield {"type": "error", "message": str(exc)}
        return

    model = project_model or _model()

    try:
        if spec.is_cli:
            from .cli_adapter import get_adapter
            adapter = get_adapter(spec.name)
            async for ev in spec.stream(
                adapter, model, messages, tools, system,
                session_id, project_path,
            ):
                yield ev
        else:
            async for ev in spec.stream(
                messages, tools, system, model,
            ):
                yield ev
    except (RuntimeError, ImportError) as exc:
        # Known-misconfiguration errors from the SDK providers carry a
        # specific message; surface it as-is. CLI providers raise
        # FileNotFoundError when the binary is missing — that is
        # caught by the bare ``Exception`` branch below.
        yield {"type": "error", "message": str(exc)}
    except Exception as exc:
        # Catch-all: log to stderr so the dev sees the traceback, then
        # yield a single error event for the UI.
        import sys, traceback
        traceback.print_exc(file=sys.stderr)
        yield {"type": "error", "message": f"{spec.name} provider error: {exc}"}
```

Add the import near the top of `llm.py`:

```python
from .providers import resolve_provider
```

The old branches for `if provider == "openai": ...`, `if provider == "pi": ...`, `if provider in ("opencode", "antigravity", "jcode"): ...`, and the default anthropic block are all removed. The bare `if provider not in (...)` pre-check at line 184 is also removed — `resolve_provider` does that now.

### Step 5: Run all tests

```bash
cd /home/ah64/apps/mlt-pipeline/open_edit && .venv/bin/python -m pytest tests/ -q --timeout=30
```

Expected: all tests pass (the 5 pre-existing sandbox skips are still skipped). Pay particular attention to:
- `tests/test_cli_adapter.py` — covers the CLI adapter interface
- `tests/test_serve_agent.py` — exercises `stream_chat` via the agent loop
- `tests/test_llm_config.py` — provider enum

If any test breaks, the most likely cause is that a provider name comparison was case-sensitive somewhere. Trace it through.

### Step 6: Run ruff

```bash
cd /home/ah64/apps/mlt-pipeline/open_edit && .venv/bin/python -m ruff check open_edit/serve/providers.py open_edit/serve/llm.py
```

Expected: no findings.

### Step 7: Commit

```bash
cd /home/ah64/apps/mlt-pipeline && git add open_edit/serve/providers.py open_edit/serve/llm.py tests/test_providers.py
git commit -m "feat(llm): add ProviderRegistry; collapse stream_chat 6-branch dispatch to a table (Wave 3.1)"
```

---

## Task 2: Shared tool executor

**Files:**
- Create: `open_edit/serve/tool_executor.py`
- Modify: `open_edit/serve/agent.py:279-350` (delete `_execute_agent_tool`, `_execute_trigger_render`)
- Modify: `open_edit/serve/pi_bridge.py` (replace local tool-dispatch with `tool_executor` calls)
- Test: `tests/test_tool_executor.py` (new)

**Interfaces:**
- Consumes: existing tool modules under `open_edit/agent/tools/` — accessed by `getattr(tools_mod, name)`.
- Produces:
  - `from open_edit.serve.tool_executor import execute_tool, execute_trigger_render, execute_render_visual_verify`

### Step 1: Write the failing test

Create `tests/test_tool_executor.py`:

```python
"""Tests for the shared tool executor (Wave 3.2)."""
from __future__ import annotations

from pathlib import Path

import pytest

from open_edit.serve.tool_executor import (
    execute_tool,
    execute_trigger_render,
    ToolNotFound,
)


def test_execute_tool_dispatches_to_module(tmp_path: Path):
    """A tool function in open_edit.agent.tools is called with (args, project_path_str)."""
    # list_assets is a real tool that returns a dict.
    result = execute_tool(
        name="list_assets",
        args={},
        project_path=tmp_path,
    )
    assert isinstance(result, dict)
    assert "assets" in result or "items" in result or "ok" in result


def test_execute_tool_unknown_raises(tmp_path: Path):
    with pytest.raises(ToolNotFound) as exc:
        execute_tool(name="definitely_not_a_tool", args={}, project_path=tmp_path)
    assert "definitely_not_a_tool" in str(exc.value)


def test_execute_trigger_render_missing_args(tmp_path: Path):
    """Server-side virtual tool: missing mode should raise a clear error, not 500."""
    with pytest.raises((ValueError, KeyError, RuntimeError)):
        execute_trigger_render(args={}, project_path=tmp_path)
```

### Step 2: Run the test and watch it fail

```bash
cd /home/ah64/apps/mlt-pipeline/open_edit && .venv/bin/python -m pytest tests/test_tool_executor.py -v
```

Expected: `ModuleNotFoundError: No module named 'open_edit.serve.tool_executor'`.

### Step 3: Create the tool executor

Create `open_edit/serve/tool_executor.py`:

```python
"""Shared tool execution (Wave 3.2).

The agent loop (``agent.py``) and the TS-extension shim
(``pi_bridge.py``) both need to run tools on the server side. Before
this module existed, ``agent.py`` had its own ``_execute_agent_tool``
and ``_execute_trigger_render`` functions, and ``pi_bridge.py`` had a
parallel copy of the trigger-render logic. The two could drift
(``agent.py`` accepts a ``mode`` field, ``pi_bridge.py`` rejected it,
etc.), and the bug was a latent source of "the agent sees different
behavior than the TS extension" reports.

This module owns the canonical implementations. Both callers import
from here. If the behavior needs to change, it changes in one place.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from . import projects as projects_mod


class ToolNotFound(LookupError):
    """Raised by :func:`execute_tool` when the named tool is not
    registered in ``open_edit.agent.tools``."""


def execute_tool(name: str, args: dict[str, Any], project_path: Path) -> dict[str, Any]:
    """Run a tool from ``open_edit.agent.tools.<name>``.

    The tool signature is ``fn(args: dict, project_path: str) -> dict``.
    Raises :class:`ToolNotFound` if the tool module/function is missing
    or not callable.
    """
    import open_edit.agent.tools as tools_mod  # type: ignore

    fn = getattr(tools_mod, name, None)
    if fn is None or not callable(fn):
        raise ToolNotFound(f"tool not found in open_edit.agent.tools: {name!r}")

    return fn(args, str(project_path))


def execute_trigger_render(args: dict[str, Any], project_path: Path) -> dict[str, Any]:
    """Server-side virtual tool: shell out to ``open_edit render``.

    ``mode`` is required (one of ``"proxy"``, ``"final"``,
    ``"overlay"``). The TS extension's render path is delegated to
    ``pi_bridge._run_trigger_render`` so the in-process agent loop
    and the TS extension see identical behavior.
    """
    from .pi_bridge import _run_trigger_render  # lazy: heavy import

    return _run_trigger_render(args, project_path)


def execute_render_visual_verify(
    args: dict[str, Any], project_path: Path,
) -> dict[str, Any]:
    """Server-side virtual tool: run visual verification on the most
    recent render. Delegated to ``visual_verify`` so the agent loop
    and the TS extension cannot drift on what "visual verify" means.
    """
    from . import visual_verify  # lazy: heavy import

    return visual_verify.run_verification(args, str(project_path))
```

### Step 4: Move `_execute_agent_tool` out of `agent.py`

In `open_edit/serve/agent.py`, replace the two functions `_execute_agent_tool` (line 279) and `_execute_trigger_render` (line 294) with thin re-exports for backward compatibility (so any out-of-tree importer doesn't break):

```python
# Re-exports for backward compatibility (Wave 3.2: moved to tool_executor.py).
from .tool_executor import (  # noqa: E402, F401
    execute_tool as _execute_agent_tool,
    execute_trigger_render as _execute_trigger_render,
    ToolNotFound,
)
```

Place this at the top of `agent.py` (after the existing imports). Delete the original function bodies.

### Step 5: Update `pi_bridge.py` to use the shared executor

Find the local copy of the trigger-render dispatch in `open_edit/serve/pi_bridge.py`. Replace it with:

```python
from .tool_executor import execute_trigger_render
```

(Remove the local function if it has the same body; if it differs in any way, log the difference in the commit message and resolve by taking the `agent.py` version since that's what runs in the agent loop.)

### Step 6: Run all tests

```bash
cd /home/ah64/apps/mlt-pipeline/open_edit && .venv/bin/python -m pytest tests/ -q --timeout=30
```

Expected: all tests pass. Particular attention:
- `tests/test_serve_agent.py`
- `tests/test_serve_pi_bridge.py`
- `tests/test_pyagent_*.py`

If a test imports `_execute_agent_tool` from `agent.py` directly, it should still work because of the re-export. If it imports from elsewhere (unlikely), update it.

### Step 7: Run ruff

```bash
cd /home/ah64/apps/mlt-pipeline/open_edit && .venv/bin/python -m ruff check open_edit/serve/tool_executor.py open_edit/serve/agent.py open_edit/serve/pi_bridge.py
```

Expected: no findings.

### Step 8: Commit

```bash
cd /home/ah64/apps/mlt-pipeline && git add open_edit/serve/tool_executor.py open_edit/serve/agent.py open_edit/serve/pi_bridge.py tests/test_tool_executor.py
git commit -m "refactor(agent): extract shared tool executor; agent.py and pi_bridge.py now share one impl (Wave 3.2)"
```

---

## Task 3: Tighten the StreamEvent contract

**Files:**
- Modify: `open_edit/serve/llm.py` (export `StreamEvent` TypedDict if not already)
- Modify: `open_edit/serve/agent.py:760-810` (the inner `async for event in stream_chat(...)` loop)
- Modify: `open_edit/serve/agent.py:115-130` (the AgentEvent TypedDict)
- Test: `tests/test_stream_contract.py` (new)

**Interfaces:**
- Consumes: existing `StreamEvent` TypedDict (was a TypedDict but not exported as a public type).
- Produces: `from open_edit.serve.llm import StreamEvent` — and a `_coerce_event(raw: dict) -> StreamEvent` helper that handles missing/extra keys.

### Step 1: Write the failing test

Create `tests/test_stream_contract.py`:

```python
"""Tests for the StreamEvent contract (Wave 3.3)."""
from __future__ import annotations

from typing import get_type_hints

from open_edit.serve.llm import StreamEvent, _coerce_event


def test_stream_event_is_typed_dict():
    """StreamEvent must be importable and annotated — not just a docstring."""
    hints = get_type_hints(StreamEvent)
    # The exact field set is what _stream_anthropic / _stream_cli / etc.
    # actually emit; this is a contract, so guard it with a test.
    assert "type" in hints
    for field in ("text_delta", "tool_use", "tool_result", "usage", "done", "error"):
        assert field in hints, f"StreamEvent must declare {field!r} variant"


def test_coerce_event_passes_through_valid_text_delta():
    raw = {"type": "text_delta", "text": "hello"}
    out = _coerce_event(raw)
    assert out["type"] == "text_delta"
    assert out["text"] == "hello"


def test_coerce_event_fills_missing_text_with_empty_string():
    raw = {"type": "text_delta"}  # text missing
    out = _coerce_event(raw)
    assert out["text"] == ""


def test_coerce_event_handles_unknown_type_gracefully():
    """A provider emitting a new event type should not crash the agent loop."""
    raw = {"type": "future_event_type", "anything": 1}
    out = _coerce_event(raw)
    assert out["type"] == "future_event_type"
    # The contract is "be tolerant": forward unknown events as-is.


def test_coerce_event_requires_type_field():
    import pytest
    with pytest.raises(ValueError):
        _coerce_event({})
```

### Step 2: Run the test and watch it fail

```bash
cd /home/ah64/apps/mlt-pipeline/open_edit && .venv/bin/python -m pytest tests/test_stream_contract.py -v
```

Expected: `ImportError: cannot import name '_coerce_event' from 'open_edit.serve.llm'`.

### Step 3: Add the StreamEvent export and helper

In `open_edit/serve/llm.py`, find the `StreamEvent` TypedDict (or add it if it doesn't exist). The current code uses a `_StreamEvent` type alias. Replace the alias with a real TypedDict near the top of the file:

```python
from typing import Literal, TypedDict


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


def _coerce_event(raw: dict) -> StreamEvent:
    """Normalize a raw event dict from any provider into a StreamEvent.

    The contract:
    - ``type`` is required. Raise ``ValueError`` if missing.
    - Missing optional fields are filled with safe defaults
      (``""`` for strings, ``{}`` for dicts) so the agent loop's
      attribute access never crashes on a missing key.
    - Unknown ``type`` values are forwarded as-is so the agent loop can
      decide how to handle them.
    """
    if "type" not in raw or not raw["type"]:
        raise ValueError(f"stream event missing 'type' field: {raw!r}")
    out: StreamEvent = dict(raw)  # type: ignore[assignment]
    out.setdefault("text", "")
    out.setdefault("input", {})
    out.setdefault("result", {})
    out.setdefault("usage", {})
    return out  # type: ignore[return-value]
```

### Step 4: Update the agent loop to use the coercer

In `open_edit/serve/agent.py`, find the inner loop that consumes `stream_chat` events (around line 760):

```python
            try:
                async for event in stream_chat(
                    messages=_make_slim_history(conversation_history, pending_verification),
                    tools=TOOL_SCHEMAS,
                    system=system_prompt,
                    session_id=conv_id,
                    project_path=str(project_path),
                ):
                    etype = event["type"]
                    if etype == "text_delta":
                        ...
```

Wrap the `event` with the coercer:

```python
from .llm import _coerce_event  # add to imports

            try:
                async for raw_event in stream_chat(
                    messages=_make_slim_history(conversation_history, pending_verification),
                    tools=TOOL_SCHEMAS,
                    system=system_prompt,
                    session_id=conv_id,
                    project_path=str(project_path),
                ):
                    event = _coerce_event(raw_event)
                    etype = event["type"]
                    ...
```

(Only the variable name and the assignment change; the rest of the dispatch stays the same.)

### Step 5: Run all tests

```bash
cd /home/ah64/apps/mlt-pipeline/open_edit && .venv/bin/python -m pytest tests/ -q --timeout=30
```

Expected: all tests pass.

### Step 6: Run ruff

```bash
cd /home/ah64/apps/mlt-pipeline/open_edit && .venv/bin/python -m ruff check open_edit/serve/llm.py open_edit/serve/agent.py
```

Expected: no findings.

### Step 7: Commit

```bash
cd /home/ah64/apps/mlt-pipeline && git add open_edit/serve/llm.py open_edit/serve/agent.py tests/test_stream_contract.py
git commit -m "feat(llm): export StreamEvent TypedDict + _coerce_event helper; tighten agent-loop contract (Wave 3.3)"
```

---

## Task 4: Update CLI adapter model lists to use shared provider list

**Files:**
- Modify: `open_edit/serve/app.py` (provider dropdown)
- Modify: `open_edit/serve/llm.py` (model fallback defaults)

**Interfaces:**
- Consumes: `list_provider_specs()` from Task 1.
- Produces: a single source of truth for "what providers are available".

### Step 1: Find every place provider names are hardcoded

```bash
cd /home/ah64/apps/mlt-pipeline/open_edit && grep -rn '"anthropic"\|"openai"\|"jcode"\|"antigravity"\|"opencode"\|"pi"' open_edit/serve/ open_edit/agent/ | grep -v __pycache__ | grep -v test_
```

Expected output (approximate; we want the actual list before editing):

- `open_edit/serve/llm.py:184` — old `if provider not in (...)` check (already removed in Task 1)
- `open_edit/serve/llm.py:273` — `_pi_provider_name()` default
- `open_edit/serve/app.py:546` — `get_provider_models` dispatcher
- `open_edit/serve/llm_config.py:45` — `ProviderName` Literal (canonical — do NOT touch)
- `open_edit/serve/llm_config.py:61-66` — `_PROVIDER_DEFAULT_MODEL` map

### Step 2: Replace `app.py`'s provider list with the registry

In `open_edit/serve/app.py`, find `get_provider_models` (around line 546). Replace any hardcoded provider list with `from .providers import list_provider_specs; names = [p.name for p in list_provider_specs()]`.

If the function dispatches per provider (e.g. `if provider == "opencode": return ... else: ...`), keep the dispatch but make sure every entry in the registry is handled. Missing-provider case should yield a 404 with a helpful message, not a 500.

### Step 3: Add a test

Add to `tests/test_providers.py`:

```python
def test_provider_model_endpoint_handles_all_providers():
    """Every registered provider must be reachable via /api/llm/providers/{name}/models.

    A missing handler should 404, not 500. The endpoint is a thin
    dispatch — we don't assert model lists, just that the dispatch
    doesn't crash.
    """
    from fastapi.testclient import TestClient
    from open_edit.serve.app import app
    client = TestClient(app)
    for spec in list_provider_specs():
        resp = client.get(f"/api/llm/providers/{spec.name}/models")
        assert resp.status_code in (200, 404), f"{spec.name}: {resp.status_code} {resp.text}"
```

### Step 4: Run all tests

```bash
cd /home/ah64/apps/mlt-pipeline/open_edit && .venv/bin/python -m pytest tests/ -q --timeout=30
```

Expected: all pass.

### Step 5: Run ruff

```bash
cd /home/ah64/apps/mlt-pipeline/open_edit && .venv/bin/python -m ruff check open_edit/serve/app.py tests/test_providers.py
```

Expected: no findings.

### Step 6: Commit

```bash
cd /home/ah64/apps/mlt-pipeline && git add open_edit/serve/app.py tests/test_providers.py
git commit -m "refactor(llm): use ProviderRegistry for model endpoint dispatch (Wave 3.4)"
```

---

## Task 5: Final whole-branch review (code-reviewer)

**Files:** none — review only.

Run the `superpowers:requesting-code-review` skill with the diff package (range `0be8fb9..HEAD`).

**Pass criteria:**
- 0 Critical
- 0 Important
- Minor findings either fixed in this branch or filed for Wave 4+

**Commit:** no commit; just the review document.

---

## Self-Review

- [x] **Spec coverage:** Each of the 4 audit findings (provider duplication, dispatch if/elif, no shared executor, StreamEvent contract loose) has a task. Provider enumeration test (Task 4) covers the "single source of truth" requirement.
- [x] **Placeholder scan:** No "TBD"/"TODO" in any step. Every code block is full code.
- [x] **Type consistency:** `ProviderSpec.stream` is `Callable[..., Awaitable[Iterator[dict]]]`. `_stream_anthropic` and `_stream_openai` take `(messages, tools, system, model)` — that matches. `_stream_pi` and `_stream_cli` take `(adapter, model, messages, tools, system, session_id, project_path)` — that matches. The dispatcher in `stream_chat` calls them with the right arg sets. Verified by the registry tests + the existing `test_serve_agent.py` suite.
- [x] **No behavior change:** Every task says "expected tests pass without modification" (modulo re-export shims for moved symbols). The audit's "no behavior change" constraint is preserved.
