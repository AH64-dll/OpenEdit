from fastapi.testclient import TestClient
from phase4_chat_ui import app as app_mod
from phase4_chat_ui.session import DEFAULT_APP

def _make_app():
    return app_mod.create_app(
        project="/tmp/nonexistent_dummy.kdenlive",
        provider="opencode-go",
        model="minimax-m3",
        default_app="piagent",
    )

def test_api_apps_lists_two_adapters():
    client = TestClient(_make_app())
    resp = client.get("/api/apps")
    assert resp.status_code == 200
    apps = {a["id"]: a for a in resp.json()["apps"]}
    assert apps["piagent"]["available"] is True
    assert apps["opencode"]["available"] is True
    # AntiGravityAdapter was removed in Task 3.2 (it was always unavailable).
    assert "antigravity" not in apps

def test_set_app_unknown_rejected():
    # Use the websocket test client if available; otherwise mark skipped.
    import pytest
    try:
        from fastapi.testclient import TestClient
    except Exception:
        pytest.skip("no testclient")
    client = TestClient(_make_app())
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # project
        ws.receive_json()  # cost
        ws.receive_json()  # state
        ws.receive_json()  # history
        ws.receive_json()  # session_list
        ws.send_json({"type": "set_app", "app_id": "nope"})
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert "nope" in msg["text"].lower() or "not available" in msg["text"].lower()
