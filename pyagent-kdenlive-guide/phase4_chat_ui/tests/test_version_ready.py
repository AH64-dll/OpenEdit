"""Phase 4 Task 5: version_list WS message (audit H2)."""
import asyncio
import uuid
from unittest.mock import AsyncMock


def test_handle_version_list_callable():
    """`handle_version_list` is the WS handler that responds to a client's
    `version_list` request with the project's render history."""
    from phase4_chat_ui.ws.handlers import handle_version_list
    assert callable(handle_version_list)


def test_handle_version_list_emits_version_list_message(tmp_path):
    """`handle_version_list` must `send_json` a `version_list` message
    containing the project's snapshots."""
    async def run() -> None:
        from phase4_chat_ui.ws.handlers import handle_version_list, get_snapshots_db_path
        from open_edit.storage.render_snapshots import (
            RenderSnapshotStore, RenderSnapshot, RenderStatus,
        )
        from datetime import datetime, timezone

        # Unique per-test project_id prevents pollution of the home-dir
        # fallback path used by `get_snapshots_db_path` for non-path ids.
        # UUID is needed because pytest reuses `tmp_path.name` across runs.
        project_id = f"p_smoke_{uuid.uuid4().hex[:8]}"
        store = RenderSnapshotStore(get_snapshots_db_path(project_id))
        store.append(RenderSnapshot(
            project_id=project_id,
            edit_graph_hash="h1",
            render_path=tmp_path / "r.mp4",
            created_at=datetime.now(timezone.utc).isoformat(),
            status=RenderStatus.ready,
            label="v1",
        ))

        ws = AsyncMock()
        broadcast = AsyncMock()
        await handle_version_list(ws, project_id, {}, broadcast)

        ws.send_json.assert_awaited_once()
        sent = ws.send_json.await_args.args[0]
        assert sent["type"] == "version_list"
        assert sent["project_id"] == project_id
        assert len(sent["versions"]) == 1
        assert sent["versions"][0]["label"] == "v1"
        assert sent["versions"][0]["status"] == "ready"
        broadcast.assert_not_awaited()
    asyncio.run(run())
