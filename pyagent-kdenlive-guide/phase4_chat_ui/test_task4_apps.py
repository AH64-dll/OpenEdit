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

def test_api_apps_lists_three_with_antigravity_unavailable():
    client = TestClient(_make_app())
    resp = client.get("/api/apps")
    assert resp.status_code == 200
    apps = {a["id"]: a for a in resp.json()["apps"]}
    assert apps["piagent"]["available"] is True
    assert apps["opencode"]["available"] is True
    assert apps["antigravity"]["available"] is False

def test_set_app_unavailable_rejected():
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
        ws.send_json({"type": "set_app", "app_id": "antigravity"})
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert "antigravity" in msg["text"].lower() or "not available" in msg["text"].lower()
