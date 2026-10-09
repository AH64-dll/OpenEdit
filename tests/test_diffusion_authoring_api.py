"""UI routes exercise the same compiler, graph transaction and stale contract."""
from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from open_edit.serve.app import app
from open_edit.serve.routers import authoring as routes
from tests.test_diffusion_authoring import (  # noqa: F401 - shared fixtures
    project,
    real_worker,
)


@pytest.mark.asyncio
async def test_source_and_property_edits_share_revision_guard(project, real_worker, monkeypatch):  # noqa: F811
    path, store = project
    async def require_project(_id):
        return SimpleNamespace(path=str(path))
    monkeypatch.setattr(routes, '_require_project', require_project)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://localhost') as client:
        url = '/api/projects/p/authoring'
        summary = await client.get(url)
        assert summary.status_code == 200
        assert 'source' not in summary.json()
        exported = (await client.get(url, params={'include_source': 'true'})).json()
        revision = exported['graph_revision']
        source = '// A UI draft\n' + exported['source']
        saved = await client.post(url, json={'expected_revision': revision, 'source': source})
        assert saved.status_code == 200
        assert saved.json()['ops_appended'] == 0
        changed = await client.post(url, json={
            'expected_revision': revision,
            'edits': [{'kind': 'set', 'source': 'index.tsx:c-hero', 'props': {'start': 2}}],
        })
        assert changed.status_code == 200
        assert store.load_all()[-1].author == 'user'
        stale = await client.post(url, json={'expected_revision': revision, 'source': source})
        assert stale.status_code == 409
        assert stale.json()['error_code'] == 'stale_revision'
        assert stale.json()['graph_revision'] == store.graph_revision()
        last_good = (await client.get(url, params={'include_source': 'true'})).json()
        assert 'A UI draft' in last_good['source']
        invalid = await client.post(url, json={
            'expected_revision': last_good['graph_revision'], 'source': '<stage />',
        })
        assert invalid.status_code == 400
        assert (await client.get(url, params={'include_source': 'true'})).json()['source'] == last_good['source']
        coerced = await client.post(url, json={'expected_revision': str(revision), 'source': source})
        assert coerced.status_code == 422
