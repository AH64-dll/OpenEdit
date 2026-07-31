"""open_edit.serve — FastAPI chat-driven backend for the Open Edit video editor.

This package is a web shell over ``open_edit.kernel``. It exposes:

- ``projects``  — project registry (list/create/get_state)
- ``llm``       — async streaming LLM client (Anthropic SDK by default)
- ``agent``     — the agent loop (``run_agent_turn`` async generator)
- ``app``       — the FastAPI app + WebSocket chat endpoint

Run the server with::

    open_edit serve
    # which is shorthand for
    uvicorn open_edit.serve.app:app --reload --host 0.0.0.0 --port 8000
"""

__all__ = ["projects", "llm", "agent", "app"]
