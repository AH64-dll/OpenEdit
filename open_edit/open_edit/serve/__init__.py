"""open_edit.serve — FastAPI chat-driven backend for the Open Edit video editor.

This package exposes:

- ``projects``  — project registry (list/create/get_state)
- ``llm``       — async streaming LLM client (Anthropic SDK by default)
- ``tool_schemas`` — hand-written function-calling schemas for the 12 agent tools
- ``agent``     — the agent loop (``run_agent_turn`` async generator)
- ``app``       — the FastAPI app + WebSocket chat endpoint

Run the server with::

    open_edit serve
    # which is shorthand for
    uvicorn open_edit.serve.app:app --reload --host 0.0.0.0 --port 8000
"""

__all__ = ["projects", "llm", "tool_schemas", "agent", "app"]
