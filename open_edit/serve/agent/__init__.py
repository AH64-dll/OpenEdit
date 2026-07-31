"""The Open Edit agent loop.

``run_agent_turn`` is an async generator that:

1. Builds a deterministic system prompt from the current project state.
2. Appends the user's message to the conversation history.
3. Streams the LLM response; for each ``tool_use`` block:
   - emits a ``tool_start`` event
   - executes the tool (via ``open_edit.agent.tools.<name>`` or via the
     server-side ``trigger_render`` virtual tool)
   - emits a ``tool_result`` event (or ``error`` if the tool raised)
4. Appends the assistant message + tool_result messages to the history.
5. Loops until the LLM returns ``end_turn``.

The conversation history is persisted as JSONL at
``<project>/.open_edit/conversations/<conv_id>.jsonl`` (one JSON message
per line).

This package is a facade: the implementation lives in
``history_store``, ``cost_sidecar``, ``prompts``, ``verify_stage``,
``loop`` and ``cli_turn``. The names below are re-exported so
``open_edit.serve.agent`` keeps the public surface of the former flat
``agent.py`` module — including the patchable seams (``stream_chat``,
``_execute_tool``, ``effective_provider``, ``_resolve_project_path``)
that tests replace via ``open_edit.serve.agent``.
"""
from __future__ import annotations

import os

# Re-exports for backward compatibility (Wave 3.2: moved to
# tool_executor.py). The ``_execute_agent_tool`` and
# ``_execute_trigger_render`` names are the historical in-process entry
# points; the canonical implementations now live in ``tool_executor.py``
# so the agent loop and the TS-extension bridge cannot drift on tool
# dispatch. ``ToolNotFound`` is re-exported for callers that previously
# imported it from this module.
from open_edit.kernel.tool_executor import (  # noqa: F401
    ToolNotFound,
    execute_tool as _execute_agent_tool,
    execute_trigger_render as _execute_trigger_render,
)

from .. import projects as projects_mod
from ..llm import effective_provider, stream_chat  # noqa: F401
from ..project_meta import is_verify_disabled  # noqa: F401

from .history_store import (  # noqa: F401
    _append_counters,
    _build_tool_result_message,
    _make_slim_history,
    _resolve_project_path,
    append_to_conversation,
    load_conversation,
    new_conversation_id,
)
from .cost_sidecar import (  # noqa: F401
    _BG_TASKS,
    _SOURCE_PRIORITY,
    _cost_sidecar_path,
    _create_bg_task,
    _load_cost_state,
    _save_cost_state,
    _save_cost_state_async,
    accumulate_usage,
    emit_cost_update,
)
from .prompts import (  # noqa: F401
    _build_state_summary,
    _build_system_prompt,
)
from .verify_stage import (  # noqa: F401
    _build_verification_result,
    _maybe_verify_render,
)
from .loop import (  # noqa: F401
    AgentEvent,
    _execute_tool,
    run_agent_turn,
)
from .cli_turn import _run_cli_owned_turn  # noqa: F401

# v1.6 polish: ``MAX_AGENT_ITERATIONS`` is a module-scope constant so
# operators can tune the runaway-loop safety cap at process start without
# editing source. Override via the ``OPEN_EDIT_AGENT_MAX_ITERATIONS`` env
# var (parsed as an int; non-integer values will raise at import time).
# It lives in the package init (not ``loop.py``) so
# ``importlib.reload(open_edit.serve.agent)`` re-reads the env var, and
# ``loop.py`` reads it through this namespace at call time.
MAX_AGENT_ITERATIONS = int(os.environ.get("OPEN_EDIT_AGENT_MAX_ITERATIONS", "10"))
