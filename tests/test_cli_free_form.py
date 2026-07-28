"""Phase 3 Task 10: `open_edit free-form` subcommand."""
import textwrap
from pathlib import Path

import pytest

from open_edit.cli import main


def test_cli_free_form_runs_script(tmp_path, capsys, monkeypatch):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / "edit_graph.db").touch()

    code_file = tmp_path / "script.py"
    code_file.write_text(textwrap.dedent('''
        # ir_api_version: 0.1; libs: {}
        # Just a header check; full e2e in test_free_form_e2e.py
    '''))

    # Use a mocked sandbox_bridge to avoid the actual Rust binary
    from open_edit.agent.exceptions import FreeFormResult
    def _mock_run(*args, **kwargs):
        return FreeFormResult.ok(ops=[], duration_s=0.0)
    monkeypatch.setattr(
        "open_edit.agent.sandbox_bridge.run_free_form", _mock_run,
    )

    rc = main(["free-form", str(code_file), str(project_dir)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "0 ops" in out
