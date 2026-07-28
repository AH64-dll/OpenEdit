"""End-to-end CLI tests for open_edit init/list/summary/undo."""
import shutil
import subprocess
from pathlib import Path

import pytest

TESTDATA = Path(__file__).parent / "testdata" / "raw_videos"


def _has_ffprobe() -> bool:
    return shutil.which("ffprobe") is not None


pytestmark = pytest.mark.skipif(
    not _has_ffprobe(), reason="ffprobe not installed"
)


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["open_edit", *args],
        capture_output=True, text=True, cwd=cwd, check=False,
    )


def test_init_ingests_videos(tmp_path: Path) -> None:
    # Copy test videos into a fresh folder
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    for f in TESTDATA.iterdir():
        shutil.copy(f, project_dir / f.name)
    # Initialize
    result = _run("init", cwd=project_dir)
    assert result.returncode == 0, result.stderr
    # Assets dir created
    assert (project_dir / ".open_edit" / "assets").exists()
    # DB created
    assert (project_dir / ".open_edit" / "edit_graph.db").exists()


def test_list_shows_no_ops_initially(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    for f in TESTDATA.iterdir():
        shutil.copy(f, project_dir / f.name)
    _run("init", cwd=project_dir)
    result = _run("list", cwd=project_dir)
    assert result.returncode == 0
    assert "0 ops" in result.stdout or "applied: 0" in result.stdout


def test_summary_shows_empty_timeline(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    for f in TESTDATA.iterdir():
        shutil.copy(f, project_dir / f.name)
    _run("init", cwd=project_dir)
    result = _run("summary", cwd=project_dir)
    assert result.returncode == 0
    assert "duration" in result.stdout.lower()
    assert "tracks" in result.stdout.lower()


def test_render_subcommand_runs(tmp_path: Path) -> None:
    """`open_edit render` runs without error on an empty project (early return)."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    for f in TESTDATA.iterdir():
        shutil.copy(f, project_dir / f.name)
    _run("init", cwd=project_dir)
    result = _run("render", cwd=project_dir)
    # Should exit 1 with "no ops" or similar
    assert result.returncode == 1
    assert "ops" in (result.stderr + result.stdout).lower() or "empty" in (result.stderr + result.stdout).lower()


def test_notes_no_subcommand_prints_usage(capsys) -> None:
    """Regression: `open_edit notes` (no subcommand) used to crash with
    NameError because cmd_notes referenced `parser_notes` (a name that
    does not exist — the local is `p_notes`, defined inside main()).
    Now it prints a usage hint and returns 0.
    """
    from open_edit import cli
    rc = cli.main(["notes"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "usage" in (captured.out + captured.err).lower()
    assert "notes" in (captured.out + captured.err).lower()
