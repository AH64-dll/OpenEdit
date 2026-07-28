"""Phase 3 Task 2: FreeFormResult + SandboxError."""
import pytest

from open_edit.agent.exceptions import FreeFormResult, SandboxError


def test_free_form_result_ok():
    r = FreeFormResult.ok(ops=[], duration_s=1.23)
    assert r.success is True
    assert r.ops == []
    assert r.duration_s == 1.23
    assert r.reason == ""
    assert r.detail == ""


def test_free_form_result_fail():
    r = FreeFormResult.fail("timeout", "30s elapsed")
    assert r.success is False
    assert r.reason == "timeout"
    assert r.detail == "30s elapsed"
    assert r.ops == []
    assert r.duration_s == 0.0


def test_sandbox_error_is_exception():
    with pytest.raises(SandboxError):
        raise SandboxError("oops")
