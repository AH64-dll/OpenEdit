"""Fixed source snapshots and actual FFmpeg publication, without a fake probe."""

import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from pydantic import ValidationError

from open_edit.kernel import export_service as export
from open_edit.kernel.render_jobs import DEFAULT_RENDER_JOB_SERVICE, RenderJobService
from open_edit.kernel.studio_service import commit_studio
from open_edit.render.profiles import profile_to_mlt_args, profile_with_quality
from open_edit.serve.app import app
from open_edit.serve.routers import exports as routes
from open_edit.storage.assets import AssetStore
from open_edit.storage.edit_graph import EditGraphStore, GraphRevisionConflict


@pytest.fixture
def project(tmp_path):
    source = tmp_path / "source.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=320x180:r=24:d=1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(source),
        ],
        check=True,
    )
    asset = AssetStore(tmp_path / ".open_edit/assets").ingest(str(source), transcribe=False)
    store = EditGraphStore(tmp_path / ".open_edit/edit_graph.db")
    # HTTP and MCP dispatchers may pass a string root, not a Path.
    commit_studio(
        str(tmp_path),
        expected_revision=0,
        changes=[],
        ops=[
            {
                "kind": "add_clip",
                "clip_id": "clip",
                "asset_hash": asset.asset_hash,
                "track_id": "video",
                "position_sec": 0,
                "out_point_sec": 1,
            }
        ],
    )
    return tmp_path, store, asset


@pytest.mark.parametrize(
    "values",
    [
        {"width": 321},
        {"fps_num": 0},
        {"fps_num": 121},
        {"range_mode": "range", "end_sec": None},
        {"range_mode": "range", "start_sec": 0.01, "end_sec": 0.011},
        {"filename": "../out"},
        {"filename": "CON"},
        {"filename": "trailing."},
        {"folder": "relative"},
        {"container": "webm"},
        {"container": "mov", "codec": "av1"},
        {"container": "mp4", "audio_codec": "opus"},
        {"container": "mkv", "audio_codec": "opus", "audio_sample_rate": 44100},
    ],
)
def test_invalid_settings_fail_before_rendering(values):
    with pytest.raises(ValidationError):
        export.ExportSettings(**values)


def test_defaults_follow_source_geometry_and_xdg_desktop(project, tmp_path, monkeypatch):
    root, store, _ = project
    config = tmp_path / "xdg"
    config.mkdir()
    (config / "user-dirs.dirs").write_text(f'XDG_DESKTOP_DIR="{tmp_path}/Local Desktop"\n')
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config))
    defaults = export.export_defaults(root)
    assert (
        defaults["settings"]["width"],
        defaults["settings"]["height"],
        defaults["settings"]["fps_num"],
    ) == (320, 180, 24)
    if __import__("os").name != "nt":
        assert defaults["settings"]["folder"] == str(tmp_path / "Local Desktop")
    assert defaults["graph_revision"] == store.graph_revision() and defaults["duration_sec"] == 1


def test_snapshot_retains_source_history_metadata_and_cas_after_later_edits(project):
    root, store, asset = project
    settings = export.ExportSettings(width=320, height=180, fps_num=24)
    payload = export.capture_export(root, store.graph_revision(), settings)
    frozen = root / ".open_edit/exports" / payload["snapshot"] / "project"
    commit_studio(
        root,
        expected_revision=store.graph_revision(),
        changes=[],
        ops=[{"kind": "remove_clip", "clip_id": "clip"}],
    )
    AssetStore(root / ".open_edit/assets").path(asset.asset_hash).unlink()
    assert export.project_timeline(root).duration_sec == 0
    assert export.project_timeline(frozen).duration_sec == 1
    assert AssetStore(frozen / ".open_edit/assets").path(asset.asset_hash).is_file()
    with pytest.raises(GraphRevisionConflict):
        export.capture_export(root, 0, settings)
    assert len(list((root / ".open_edit/exports").iterdir())) == 1


@pytest.mark.parametrize(
    "container,audio_codec,audio",
    [("mp4", "aac", True), ("mov", "aac", False), ("mkv", "pcm_s16le", True)],
)
def test_actual_publication_is_verified_unique_and_preserves_existing_files(
    project, tmp_path, container, audio_codec, audio
):
    root, _, _ = project
    settings = export.ExportSettings(
        filename="My edit",
        folder=str(tmp_path / "Local Desktop"),
        width=320,
        height=180,
        fps_num=24,
        container=container,
        audio_codec=audio_codec,
        audio=audio,
    )
    first, report = export.publish_export(root / "source.mp4", settings, 1)
    original = first.read_bytes()
    second, again = export.publish_export(root / "source.mp4", settings, 1)
    assert first.name == f"My edit.{container}" and second.name == f"My edit (2).{container}"
    assert first.read_bytes() == original and report["passed"] and again["full_decode"]
    assert report["audio"] == audio
    assert not list(first.parent.glob(".openedit-export-*"))


def test_failed_verification_never_publishes_an_output(project, tmp_path):
    root, _, _ = project
    settings = export.ExportSettings(
        folder=str(tmp_path / "Desktop"), width=640, height=360, fps_num=24
    )
    with pytest.raises(ValueError, match="dimensions"):
        export.publish_export(root / "source.mp4", settings, 1)
    assert not list((tmp_path / "Desktop").iterdir())


def test_custom_profile_uses_geometry_fps_and_correct_aspect():
    profile = profile_with_quality(
        None,
        "final",
        overrides={"width": 1080, "height": 1920, "frame_rate_num": 24000, "frame_rate_den": 1001},
    )
    args = profile_to_mlt_args(profile, backend="cpu")
    assert (
        "s=1080x1920" in args and "display_aspect_num=9" in args and "display_aspect_den=16" in args
    )
    assert "frame_rate_num=24000" in args and "custom:1080x1920@24000/1001" in profile.name


@pytest.mark.asyncio
async def test_export_http_captures_revision_and_verified_file_actions(project, monkeypatch):
    root, store, _ = project

    async def require(_):
        return SimpleNamespace(path=str(root))

    monkeypatch.setattr(routes, "_require_project", require)

    async def launch(path, job_id, mode):
        payload = DEFAULT_RENDER_JOB_SERVICE.get(path, job_id).params["export"]
        assert (
            export.project_timeline(
                path / ".open_edit/exports" / payload["snapshot"] / "project"
            ).duration_sec
            == 1
        )
        return {
            "ok": True,
            "output_path": str(root / "source.mp4"),
            "export_verification": {"passed": True},
            "mode": mode,
        }

    monkeypatch.setattr(DEFAULT_RENDER_JOB_SERVICE, "_launch", launch)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        defaults = (await client.get("/api/projects/p/export/settings")).json()
        response = await client.post(
            "/api/projects/p/export",
            json={"expected_revision": store.graph_revision(), "settings": defaults["settings"]},
        )
        assert response.status_code == 202, response.text
        job = await DEFAULT_RENDER_JOB_SERVICE.wait(root, response.json()["job_id"])
        assert job.status == "succeeded" and job.graph_revision == store.graph_revision()
        assert (
            await client.get(
                f"/api/projects/p/exports/{job.job_id}/file", headers={"Range": "bytes=0-99"}
            )
        ).status_code == 206
        assert (await client.get("/api/projects/p/exports/unknown/file")).status_code == 404
        invoked = []
        if __import__("os").name == "nt":
            monkeypatch.setattr(routes.os, "startfile", lambda path: invoked.append(path))
        else:
            monkeypatch.setattr(
                routes.subprocess, "Popen", lambda args, **kwargs: invoked.append(args)
            )
        assert (
            await client.post(f"/api/projects/p/exports/{job.job_id}/open/folder")
        ).status_code == 200
        assert invoked
        rejected = await client.post(
            "/api/projects/p/export",
            json={"expected_revision": 0, "settings": defaults["settings"]},
        )
        assert rejected.status_code == 409
        check = await client.post('/api/projects/p/preview/check', json={
            'expected_revision': store.graph_revision(), 'start_sec': .25, 'end_sec': .75})
        assert check.status_code == 202, check.text
        checked = await DEFAULT_RENDER_JOB_SERVICE.wait(root, check.json()['job_id'])
        options = checked.params['export']['settings']
        assert checked.status == 'succeeded' and options['folder'] == str(root / '.open_edit/cache/checks')
        assert (options['width'],options['height'],options['fps_num']) == (320,180,24)
        assert options['range_mode'] == 'range' and options['quality'] == 'high'
        invalid = await client.post('/api/projects/p/preview/check', json={
            'expected_revision': store.graph_revision(), 'start_sec': .75, 'end_sec': .25})
        assert invalid.status_code == 400


@pytest.mark.asyncio
@pytest.mark.browser
async def test_actual_fixed_revision_range_export_to_local_folder(project, monkeypatch):
    if not shutil.which("melt"):
        pytest.skip("Actual MLT is required")
    root, store, _ = project
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    settings = export.ExportSettings(
        filename="Final",
        folder=str(root / "Desktop"),
        width=320,
        height=180,
        fps_num=24,
        encoder="cpu",
        range_mode="range",
        start_sec=0.25,
        end_sec=0.75,
    )
    payload = export.capture_export(root, store.graph_revision(), settings)
    service = RenderJobService()
    job = service.enqueue(
        "range", root, "final", expected_revision=store.graph_revision(), params={"export": payload},
    )
    commit_studio(
        root,
        expected_revision=store.graph_revision(),
        changes=[],
        ops=[{"kind": "remove_clip", "clip_id": "clip"}],
    )
    completed = await service.wait(root, job.job_id)
    assert completed.status == "succeeded", completed.error
    result = completed.result
    assert not (root / ".open_edit/exports" / payload["snapshot"]).exists()
    await service.shutdown()
    assert result["ok"] and result["export_verification"]["full_decode"]
    assert Path(result["output_path"]).parent == root / "Desktop" and result["duration_sec"] == 0.5
    artifacts = Path("tests/browser/artifacts")
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "local-export-verification.json").write_text(
        json.dumps(result["export_verification"])
    )


@pytest.mark.asyncio
async def test_queued_export_cancellation_reclaims_only_snapshot(project):
    root, store, asset = project
    source = AssetStore(root / ".open_edit/assets").path(asset.asset_hash)
    original = source.read_bytes()
    payload = export.capture_export(root, store.graph_revision(), export.ExportSettings(folder=str(root / "out")))
    stage = root / ".open_edit/exports" / payload["snapshot"]
    service = RenderJobService()
    job = service.enqueue("queued", root, "final", params={"export": payload})
    try:
        await service.cancel(root, job.job_id)
        assert service.get(root, job.job_id).status == "cancelled"
        assert not stage.exists()
        assert source.read_bytes() == original
    finally:
        await service.shutdown()


@pytest.mark.asyncio
async def test_terminal_snapshot_waits_for_other_active_reference(project):
    root, store, _ = project
    payload = export.capture_export(root, store.graph_revision(), export.ExportSettings(folder=str(root / "out")))
    stage = root / ".open_edit/exports" / payload["snapshot"]
    service = RenderJobService()
    first = service.enqueue("shared", root, "final", encoder_backend="cpu", params={"export": payload})
    second = service.enqueue("shared", root, "final", encoder_backend="gpu", params={"export": payload})
    service._update(root, first.job_id, "failed", error="recorded failure")
    try:
        assert not export._discard_export_snapshot(root, payload)
        assert stage.exists()
        await service.cancel(root, second.job_id)
        assert not stage.exists()
        assert service.get(root, first.job_id).error == "recorded failure"
    finally:
        await service.shutdown()


@pytest.mark.asyncio
async def test_orphan_recovery_keeps_live_producer_then_reclaims_stage(project):
    import sys

    root, store, _ = project
    payload = export.capture_export(root, store.graph_revision(), export.ExportSettings(folder=str(root / "out")))
    stage = root / ".open_edit/exports" / payload["snapshot"]
    service = RenderJobService()
    job = service.enqueue("orphan", root, "final", params={"export": payload})
    child = subprocess.Popen(
        [sys.executable, "-u", "-c",
         "import sys,time; from pathlib import Path; "
         "from open_edit.kernel.render_jobs import _project_lease,_try_lease; "
         "lease_context=_project_lease(Path(sys.argv[1])); lease=lease_context.__enter__(); "
         "assert _try_lease(lease); print('locked',flush=True); time.sleep(60)",
         str(stage / "project")],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        assert child.stdout.readline().strip() == "locked"
        recovery = RenderJobService()
        recovery.recover(root)
        assert recovery.get(root, job.job_id).status == "orphaned"
        assert stage.exists()
        error = recovery.get(root, job.job_id).error
        child.kill()
        child.wait(timeout=5)
        recovery.recover(root)
        assert not stage.exists()
        assert recovery.get(root, job.job_id).error == error
    finally:
        if child.poll() is None:
            child.kill()
        child.wait()
        child.stdout.close()
        child.stderr.close()
        await service.shutdown()


@pytest.mark.asyncio
async def test_terminal_cleanup_preserves_published_user_file_inside_snapshot(project):
    root, store, _ = project
    payload = export.capture_export(root, store.graph_revision(), export.ExportSettings(folder=str(root / "out")))
    stage = root / ".open_edit/exports" / payload["snapshot"]
    published = stage / "user-export.mp4"
    published.write_bytes(b"published user data")
    service = RenderJobService()
    job = service.enqueue("publication", root, "final", params={"export": payload})
    service._update(root, job.job_id, "succeeded", output_path=str(published))
    try:
        service._cleanup_terminal_exports(root)
        assert published.read_bytes() == b"published user data"
        assert service.get(root, job.job_id).output_path == str(published)
    finally:
        await service.shutdown()
