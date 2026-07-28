"""Tests for ``open_edit.serve.logging_setup``.

Covers:

* ``setup_logging`` runs (and re-runs) without error and is idempotent.
* The correlation context vars get/set/bind correctly and are isolated
  per asyncio task.
* ``CorrelationIdMiddleware`` mints a request id, echoes it back in the
  ``X-Request-ID`` response header, and honours an inbound header.
* ``get_logger`` records carry the current context (via the JSON
  formatter) with no filesystem/network side effects.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from open_edit.serve import logging_setup as ls  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_context():
    """Reset every correlation var before and after each test."""
    for var in ls._CONTEXT_VARS.values():
        var.set(None)
    yield
    for var in ls._CONTEXT_VARS.values():
        var.set(None)


# ---------------------------------------------------------------------------
# setup_logging
# ---------------------------------------------------------------------------

def test_setup_logging_runs_and_is_idempotent():
    root = logging.getLogger()
    ls.setup_logging("DEBUG")
    count_after_first = len(root.handlers)
    ls.setup_logging("INFO")
    assert len(root.handlers) == count_after_first
    assert root.level == logging.INFO


def test_setup_logging_bad_level_falls_back_to_info():
    ls.setup_logging("NOT_A_LEVEL")
    assert logging.getLogger().level == logging.INFO


# ---------------------------------------------------------------------------
# Context vars
# ---------------------------------------------------------------------------

def test_get_set_helpers_roundtrip():
    ls.set_request_id("req-1")
    ls.set_project_id("proj-1")
    ls.set_conversation_id("conv-1")
    ls.set_job_id("job-1")
    assert ls.get_request_id() == "req-1"
    assert ls.get_project_id() == "proj-1"
    assert ls.get_conversation_id() == "conv-1"
    assert ls.get_job_id() == "job-1"


def test_bind_context_sets_multiple():
    ls.bind_context(project_id="p", job_id="j")
    ctx = ls.get_context()
    assert ctx["project_id"] == "p"
    assert ctx["job_id"] == "j"
    assert ctx["request_id"] is None


def test_bind_context_unknown_key_raises():
    with pytest.raises(KeyError):
        ls.bind_context(not_a_var="x")


def test_context_isolated_per_task():
    async def _worker(value: str) -> str | None:
        ls.set_request_id(value)
        await asyncio.sleep(0.01)
        return ls.get_request_id()

    async def _main() -> list[str | None]:
        return await asyncio.gather(_worker("a"), _worker("b"), _worker("c"))

    results = asyncio.run(_main())
    assert sorted(r for r in results if r) == ["a", "b", "c"]
    # The outer context is untouched by the child tasks.
    assert ls.get_request_id() is None


# ---------------------------------------------------------------------------
# get_logger / JSON formatter
# ---------------------------------------------------------------------------

def test_logger_record_includes_context():
    logger = ls.get_logger("open_edit.test.ctx")
    logger.propagate = False
    logger.setLevel(logging.INFO)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(ls.JsonFormatter())
    handler.addFilter(ls.ContextFilter())
    logger.addHandler(handler)
    try:
        ls.bind_context(request_id="rid-42", project_id="pid-9")
        logger.info("hello", extra={"custom": "field"})
    finally:
        logger.removeHandler(handler)

    payload = json.loads(stream.getvalue().strip())
    assert payload["message"] == "hello"
    assert payload["request_id"] == "rid-42"
    assert payload["project_id"] == "pid-9"
    assert payload["custom"] == "field"
    assert "conversation_id" not in payload


# ---------------------------------------------------------------------------
# CorrelationIdMiddleware
# ---------------------------------------------------------------------------

def _build_app():
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route

    async def _echo(request):
        return PlainTextResponse(ls.get_request_id() or "")

    app = Starlette(routes=[Route("/echo", _echo)])
    app.add_middleware(ls.CorrelationIdMiddleware)
    return app


def test_middleware_sets_response_header():
    from starlette.testclient import TestClient

    with TestClient(_build_app()) as client:
        resp = client.get("/echo")
    assert resp.status_code == 200
    assert resp.headers[ls.REQUEST_ID_HEADER]
    # The id bound in-context is the one echoed back.
    assert resp.text == resp.headers[ls.REQUEST_ID_HEADER]


def test_middleware_honours_inbound_header():
    from starlette.testclient import TestClient

    with TestClient(_build_app()) as client:
        resp = client.get("/echo", headers={ls.REQUEST_ID_HEADER: "client-supplied"})
    assert resp.headers[ls.REQUEST_ID_HEADER] == "client-supplied"
    assert resp.text == "client-supplied"


def test_middleware_resets_context_after_request():
    from starlette.testclient import TestClient

    with TestClient(_build_app()) as client:
        client.get("/echo")
    assert ls.get_request_id() is None
