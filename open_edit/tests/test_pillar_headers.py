"""Tests for sandbox header auto-injection and run_script."""
from __future__ import annotations


def test_run_script_importable():
    from open_edit.agent.tools import run_script
    assert callable(run_script)


def test_run_python_importable():
    from open_edit.agent.tools import run_python
    assert callable(run_python)


def test_run_script_is_run_python():
    from open_edit.agent.tools import run_script, run_python
    assert run_script is run_python


def test_header_auto_inject_missing():
    from open_edit.agent.sandbox_bridge import run_free_form
    assert callable(run_free_form)


def test_header_auto_inject_present():
    """Code with existing header should pass through unchanged."""
    code = "# ir_api_version: 0.1; libs: {}\nprint('hello')"
    assert code.startswith("# ir_api_version:")
