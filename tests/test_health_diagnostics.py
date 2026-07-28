"""Tests for /health, /diagnostics, and token auth middleware."""
from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient
from starlette.requests import Request
from starlette.responses import Response

from open_edit.serve.app import TokenAuthMiddleware, app

client = TestClient(app)


def test_health_ok() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert "status" in body


def test_diagnostics_ok_without_token() -> None:
    resp = client.get("/diagnostics")
    assert resp.status_code == 200
    body = resp.json()
    for key in ("mlt_available", "sandbox_available", "sqlite_version"):
        assert key in body


def _remote_request(path: str, headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "scheme": "http",
        "server": ("example.com", 80),
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": headers or [],
        "client": ("203.0.113.7", 40000),
    }
    return Request(scope)


async def _ok_call_next(_request: Request) -> Response:
    return Response("ok", status_code=200)


def test_remote_missing_token_401(monkeypatch) -> None:
    monkeypatch.setenv("OPEN_EDIT_TOKEN", "s3cret")
    mw = TokenAuthMiddleware(app)
    request = _remote_request("/diagnostics")
    resp = asyncio.run(mw.dispatch(request, _ok_call_next))
    assert resp.status_code == 401
    import json

    body = json.loads(bytes(resp.body))
    assert body["error"]["code"] == "auth_required"


def test_remote_valid_token_200(monkeypatch) -> None:
    monkeypatch.setenv("OPEN_EDIT_TOKEN", "s3cret")
    mw = TokenAuthMiddleware(app)
    request = _remote_request(
        "/diagnostics", headers=[(b"authorization", b"Bearer s3cret")]
    )
    resp = asyncio.run(mw.dispatch(request, _ok_call_next))
    assert resp.status_code == 200


def test_remote_health_exempt(monkeypatch) -> None:
    monkeypatch.setenv("OPEN_EDIT_TOKEN", "s3cret")
    mw = TokenAuthMiddleware(app)
    request = _remote_request("/health")
    resp = asyncio.run(mw.dispatch(request, _ok_call_next))
    assert resp.status_code == 200
