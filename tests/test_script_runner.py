"""Real subprocess lifecycle and graphics-output regression tests."""
import os
import subprocess
import sys
import time

import pytest

from open_edit.agent.script_runner import run_free_form, run_render
from open_edit.agent.script_runner.execution import execute_python
from open_edit.storage.edit_graph import EditGraphStore


@pytest.fixture
def workdir(tmp_path):
    EditGraphStore(tmp_path / 'edit_graph.db')
    return tmp_path


def test_output_is_drained_and_bounded(workdir):
    proc, duration = execute_python(
        ['-c', "import sys; print('x' * 200000); sys.stderr.write('y' * 200000)"],
        workdir, 5,
    )
    assert proc.returncode == 0
    assert 0 < len(proc.stdout) <= 65536
    assert 0 < len(proc.stderr) <= 65536
    assert duration > 0


def test_script_timeout_releases_lock_and_cleans_staging(workdir):
    result = run_free_form('import time; time.sleep(20)', workdir, 'p', 'e', timeout=1)
    assert not result.success
    assert result.reason == 'script_timeout'
    assert list((workdir / '.script-runs').iterdir()) == []
    assert run_free_form('print("hello")', workdir, 'p', 'e').success


@pytest.mark.skipif(os.name != 'posix', reason='POSIX process-group lifecycle')
def test_timeout_terminates_spawned_children(workdir):
    marker = workdir / 'child-finished'
    child = f"import time; from pathlib import Path; time.sleep(2); Path({str(marker)!r}).touch()"
    parent = f"import subprocess, time; subprocess.Popen([{sys.executable!r}, '-c', {child!r}]); time.sleep(20)"
    with pytest.raises(subprocess.TimeoutExpired):
        execute_python(['-c', parent], workdir, 1)
    time.sleep(1.3)
    assert not marker.exists()


def test_graphics_output_and_path_validation(workdir):
    out = workdir / 'nested' / 'out.mp4'
    code = "import os; from pathlib import Path; Path(os.environ['OUTPUT_PATH']).write_bytes(b'video')"
    assert run_render(code, workdir, out).ok
    assert out.read_bytes() == b'video'
    assert not run_render(code, workdir, workdir.parent / 'outside.mp4').ok
    assert not list(workdir.glob('render-*'))


def test_old_output_cannot_mask_missing_new_output(workdir):
    out = workdir / 'out.mp4'
    out.write_bytes(b'previous')
    assert not run_render('pass', workdir, out).ok
    assert out.read_bytes() == b'previous'


def test_render_failure_is_bounded_and_keeps_previous_output(workdir):
    out = workdir / 'out.mp4'
    out.write_bytes(b'previous')
    result = run_render("raise RuntimeError('/private/secret')", workdir, out)
    assert not result.ok
    assert '/private/secret' not in result.detail
    assert out.read_bytes() == b'previous'
    assert not run_render('import time; time.sleep(20)', workdir, out, timeout_sec=1).ok
    assert not list(workdir.glob('render-*'))
