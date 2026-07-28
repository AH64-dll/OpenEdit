"""Test that GET /api/projects/{id} includes timeline_full."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from open_edit.serve.app import app

client = TestClient(app)


def test_project_state_includes_timeline_full() -> None:
    """An existing project should return timeline_full with tracks/clips."""
    resp = client.get("/api/projects")
    assert resp.status_code == 200
    projects = resp.json()
    if not projects:
        pytest.skip("no projects to test with")
    project_id = projects[0]["id"]
    resp = client.get(f"/api/projects/{project_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "timeline_full" in data
    if data["timeline_full"] is not None:
        full = data["timeline_full"]
        assert "tracks" in full
        assert "duration_sec" in full
        assert isinstance(full["tracks"], list)
