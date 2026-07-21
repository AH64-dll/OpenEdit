"""Phase 3 Task 8: sandbox_bridge unit tests with mocked Rust binary.

Note: The brief's test draft had two bugs vs. the real code:
  1. _FlushingBuffer() needs an ops_file argument (the brief's class signature
     takes one, but the test draft called it with no args).
  2. AddClipOp has no `project_id` field — only `parent_id` (inherited from
     Operation). The test draft passed `project_id="p"` which Pydantic rejects.

Both are fixed here. The intent of H10 (write-first-then-append) and the
structural check on the rendered bootstrap are preserved.
"""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from open_edit.agent.sandbox_bridge import (
    _render_bootstrap, _FlushingBuffer,
)
from open_edit.agent.exceptions import FreeFormResult


@pytest.fixture(autouse=True)
def _allow_tmp_workdir(tmp_path, monkeypatch):
    """P9: permit workdirs under the test's tmp_path by default.

    Most tests use `tmp_path / "proj"` as the workdir. Without this fixture,
    the new workdir validation would reject those tests because they live
    under /tmp/.../..., not under the process's cwd. Tests that need a
    NARROWER allowed root override this by calling monkeypatch.setenv
    themselves; pytest gives them the same monkeypatch instance.
    """
    monkeypatch.setenv("OPEN_EDIT_PROJECTS_ROOT", str(tmp_path))


def test_flushing_buffer_writes_first_then_appends(tmp_path):
    """H10: write first, then append; failed write raises."""
    ops_file = tmp_path / "ops.jsonl"
    buf = _FlushingBuffer(ops_file)
    from open_edit.ir.types import AddClipOp, new_id
    op = AddClipOp(
        edit_id=new_id(), author="ai", parent_id="e",
        clip_id="c1", asset_hash="abc", track_id="t1", position_sec=0.0,
    )
    buf.append(op)
    assert ops_file.exists()
    assert len(buf) == 1
    # Each line is a valid JSON op
    parsed = json.loads(ops_file.read_text().strip())
    assert parsed["kind"] == "add_clip"
    assert parsed["clip_id"] == "c1"


def test_render_bootstrap_is_self_contained():
    """C2: bootstrap does NOT `import open_edit`."""
    bootstrap = _render_bootstrap(project_id="p1", parent_op_id="e1")
    # The bootstrap should inline the IR class; no `from open_edit` import
    # for IR/op models (the imports block only has typing/pydantic/datetime).
    assert "from open_edit.ir.api import IR" not in bootstrap
    # The IR class should be inlined
    assert "class IR:" in bootstrap
    # The 12 op models should be inlined (at least the class names)
    for cls in ["AddClipOp", "TrimClipOp", "FreeFormCodeOp"]:
        assert f"class {cls}" in bootstrap
    # Project and parent IDs are injected
    assert "'p1'" in bootstrap
    assert "'e1'" in bootstrap
    # OPS_FILE is /scratch/ops.jsonl (in-sandbox path, C1)
    assert '"/scratch/ops.jsonl"' in bootstrap


def test_render_bootstrap_inlines_all_op_classes():
    """C1 follow-up: bootstrap must inline a class definition for every op in OperationUnion.

    Self-enforcing: derives the expected set from `OperationUnion` itself via
    `typing.get_args`, not a hardcoded list. Adding a 25th op class to
    `OperationUnion` (and forgetting to add it to `op_types` in
    `sandbox_bridge._render_bootstrap`) will fail this test with a clear
    "Missing op class definitions" message naming the missing op.
    """
    from typing import get_args
    from open_edit.ir.types import OperationUnion

    # OperationUnion is `Annotated[Union[...], Field(...)]`. Unwrap the
    # Annotated to get the Union, then get_args() to list all op classes.
    _op_union, _ = get_args(OperationUnion)
    op_classes = get_args(_op_union)  # tuple of all op classes
    expected_names = {cls.__name__ for cls in op_classes}

    bootstrap = _render_bootstrap(project_id="p1", parent_op_id="e1")

    missing = sorted(
        name for name in expected_names
        if f"class {name}" not in bootstrap
    )
    assert not missing, (
        f"Missing op class definitions in bootstrap: {missing}. "
        f"Either add them to `op_types` in "
        f"open_edit/agent/sandbox_bridge.py:_render_bootstrap, "
        f"or this is a regression of the C1 fix."
    )


def test_bootstrap_exec_instantiates_all_24_op_classes(tmp_path):
    """C1 (final-fixes): executing the bootstrap must make every op class
    available in scope (no NameError when IR methods construct them).
    """
    bootstrap = _render_bootstrap(
        project_id="p1",
        parent_op_id="e1",
        originating_note_id="n1",
    )
    # Run the bootstrap in an isolated globals dict, like the Rust binary does
    g: dict = {"__name__": "__sandbox__", "__file__": "<bootstrap>"}
    exec(compile(bootstrap, "<bootstrap>", "exec"), g)

    # Every op class name must be reachable in the bootstrap's globals
    expected = [
        "AddClipOp", "RemoveClipOp", "MoveClipOp", "TrimClipOp",
        "AddTransitionOp", "RemoveTransitionOp", "SetTransitionPropertyOp",
        "AddEffectOp", "RemoveEffectOp", "SetEffectParamOp",
        "SetKeyframeOp", "RemoveKeyframeOp",
        "SlipClipOp", "RippleDeleteClipOp", "ChangeClipSpeedOp",
        "SplitClipOp", "ReplaceClipSourceOp", "SetClipSpeedRampOp",
        "SetAudioGainOp", "NormalizeAudioOp",
        "GroupEditsOp", "UngroupEditsOp",
        "RawMltXmlOp", "FreeFormCodeOp",
    ]
    for name in expected:
        assert name in g, f"{name} not in bootstrap scope after exec"

    # `ir` instance must be present and must accept a method that was added
    # in T7 (was NameError before the fix).
    assert "ir" in g
    # Wire a buffer; IR will append a SlipClipOp
    import json
    ops_file = tmp_path / "ops.jsonl"
    class _Buf(list):
        def append(self, op):
            super().append(op)
            with open(ops_file, "a") as f:
                f.write(op.model_dump_json() + "\n")
    g["_ops"] = _Buf()
    g["ir"] = g["IR"](
        g["_ops"],
        project_id="p1",
        parent_op_id="e1",
        originating_note_id="n1",
    )
    # Calling a T7 method must not raise NameError
    g["ir"].slip_clip(clip_id="c1", delta_sec=0.5)
    assert ops_file.exists()
    lines = [ln for ln in ops_file.read_text().splitlines() if ln.strip()]
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["kind"] == "slip_clip"
    assert parsed["parent_id"] == "e1"


def test_run_free_form_missing_header_returns_preflight_failed(tmp_path):
    """No # ir_api_version: header → FreeFormResult.fail('preflight_failed')."""
    from open_edit.agent.sandbox_bridge import run_free_form
    workdir = tmp_path / "proj"
    workdir.mkdir()
    (workdir / "edit_graph.db").touch()
    result = run_free_form(
        code="import os  # no header",
        workdir=workdir,
        project_id="p1",
        parent_op_id="e1",
    )
    assert not result.success
    assert result.reason == "preflight_failed"


def test_run_free_form_unsupported_version_returns_fail(tmp_path):
    from open_edit.agent.sandbox_bridge import run_free_form
    workdir = tmp_path / "proj"
    workdir.mkdir()
    (workdir / "edit_graph.db").touch()
    result = run_free_form(
        code="# ir_api_version: 99.0; libs: {}",
        workdir=workdir,
        project_id="p1",
        parent_op_id="e1",
    )
    assert not result.success
    assert result.reason == "ir_api_version_unsupported"


def test_run_free_form_unsupported_lib_returns_fail(tmp_path):
    from open_edit.agent.sandbox_bridge import run_free_form
    workdir = tmp_path / "proj"
    workdir.mkdir()
    (workdir / "edit_graph.db").touch()
    result = run_free_form(
        code='# ir_api_version: 0.1; libs: {"numpy": "99.0"}',
        workdir=workdir,
        project_id="p1",
        parent_op_id="e1",
    )
    assert not result.success
    assert result.reason == "lib_version_unsupported"


def test_run_free_form_clamps_timeout_and_mem():
    """H9: hard caps MAX_FREEFORM_TIMEOUT_SEC=300, MAX_FREEFORM_MEM_MB=4096."""
    from open_edit.agent.sandbox_bridge import (
        MAX_FREEFORM_TIMEOUT_SEC, MAX_FREEFORM_MEM_MB, run_free_form,
    )
    # Test the constants exist with the right values
    assert MAX_FREEFORM_TIMEOUT_SEC == 300
    assert MAX_FREEFORM_MEM_MB == 4096
    # Note: full behavior test requires a real (or mocked) Rust binary;
    # covered in test_free_form_e2e.py.


@patch("open_edit.agent.sandbox_bridge.subprocess.run")
def test_timeout_clamped_to_max(mock_run, tmp_path):
    """T5: a timeout > MAX_FREEFORM_TIMEOUT_SEC is clamped before reaching the binary."""
    from open_edit.agent.sandbox_bridge import (
        run_free_form, MAX_FREEFORM_TIMEOUT_SEC,
    )
    workdir = tmp_path / "proj"
    workdir.mkdir()
    (workdir / "edit_graph.db").touch()

    mock_run.return_value = MagicMock(
        returncode=0,
        stdout='{"exit_code":0,"ok":true,"stderr":""}\n',
    )
    run_free_form(
        code="# ir_api_version: 0.1; libs: {}",
        workdir=workdir,
        project_id="p1",
        parent_op_id="e1",
        timeout=999_999,
    )
    cmd = mock_run.call_args[0][0]
    assert "--timeout" in cmd, f"expected --timeout in {cmd}"
    idx = cmd.index("--timeout")
    assert cmd[idx + 1] == str(MAX_FREEFORM_TIMEOUT_SEC), \
        f"expected {MAX_FREEFORM_TIMEOUT_SEC}, got {cmd[idx + 1]}"


@patch("open_edit.agent.sandbox_bridge.subprocess.run")
def test_mem_mb_clamped_to_max(mock_run, tmp_path):
    """T5: a mem_mb > MAX_FREEFORM_MEM_MB is clamped before reaching the binary."""
    from open_edit.agent.sandbox_bridge import (
        run_free_form, MAX_FREEFORM_MEM_MB,
    )
    workdir = tmp_path / "proj"
    workdir.mkdir()
    (workdir / "edit_graph.db").touch()

    mock_run.return_value = MagicMock(
        returncode=0,
        stdout='{"exit_code":0,"ok":true,"stderr":""}\n',
    )
    run_free_form(
        code="# ir_api_version: 0.1; libs: {}",
        workdir=workdir,
        project_id="p1",
        parent_op_id="e1",
        mem_mb=999_999,
    )
    cmd = mock_run.call_args[0][0]
    assert "--mem" in cmd, f"expected --mem in {cmd}"
    idx = cmd.index("--mem")
    assert cmd[idx + 1] == str(MAX_FREEFORM_MEM_MB), \
        f"expected {MAX_FREEFORM_MEM_MB}, got {cmd[idx + 1]}"


def test_run_free_form_sandbox_binary_missing(tmp_path):
    """P8: no allow-listed binary → FreeFormResult.fail('sandbox_binary_missing').

    The resolver must consult an absolute allow-list, not $PATH; if no
    candidate exists it raises FileNotFoundError and the bridge maps that
    to a sandbox_binary_missing result.
    """
    from open_edit.agent.sandbox_bridge import run_free_form
    workdir = tmp_path / "proj"
    workdir.mkdir()
    (workdir / "edit_graph.db").touch()
    with patch(
        "open_edit.agent.sandbox_bridge._resolve_sandbox_bin",
        side_effect=FileNotFoundError("not in any known location"),
    ):
        result = run_free_form(
            code="# ir_api_version: 0.1; libs: {}",
            workdir=workdir,
            project_id="p1",
            parent_op_id="e1",
        )
    assert not result.success
    assert result.reason == "sandbox_binary_missing"


def test_resolve_sandbox_bin_ignores_path(monkeypatch, tmp_path):
    """P8: a hostile 'open-edit-sandbox' on $PATH must NOT be picked up.

    The new resolver looks only at an absolute allow-list (~/.local/bin,
    /usr/local/bin, the repo's target/release). It never consults $PATH
    via shutil.which, so a planted attacker binary on PATH cannot win
    even if it appears earlier than the legitimate one.
    """
    from open_edit.agent.sandbox_bridge import _resolve_sandbox_bin

    hostile_dir = tmp_path / "hostile_dir"
    hostile_dir.mkdir()
    hostile_bin = hostile_dir / "open-edit-sandbox"
    hostile_bin.write_text("#!/bin/sh\necho hostile\n")
    hostile_bin.chmod(0o755)
    monkeypatch.setenv("PATH", f"{hostile_dir}:")

    # Make every allow-list candidate's .exists() return False so the
    # resolver finds nothing. If the implementation falls back to
    # shutil.which/PATH, it would find the hostile binary and return
    # its path instead of raising.
    with patch.object(Path, "exists", return_value=False):
        with pytest.raises(FileNotFoundError):
            _resolve_sandbox_bin()


def test_resolve_sandbox_bin_finds_allowlisted(monkeypatch, tmp_path):
    """P8: a binary at ~/.local/bin/open-edit-sandbox IS found (allow-list
    member, not a PATH hit).
    """
    from open_edit.agent.sandbox_bridge import _resolve_sandbox_bin

    fake = tmp_path / ".local" / "bin" / "open-edit-sandbox"
    fake.parent.mkdir(parents=True)
    fake.write_text("#!/bin/sh\necho legit\n")
    fake.chmod(0o755)
    monkeypatch.setenv("HOME", str(tmp_path))

    found = _resolve_sandbox_bin()
    assert found is not None
    assert Path(found).resolve() == fake.resolve()


# =========================================================================
# P9: workdir must be validated against an allowed-root allow-list before
# any host-side staging (code.py, _render_code.py, bootstrap.py).
# A tool call with project_path="/etc" must NOT write into /etc.
# =========================================================================

def test_run_free_form_rejects_workdir_outside_allowed_root(tmp_path, monkeypatch):
    """P9: a workdir that LOOKS like a real project (has edit_graph.db) but
    lives outside OPEN_EDIT_PROJECTS_ROOT must be rejected with
    reason='invalid_argument' and produce no host-side staging files.
    """
    from open_edit.agent.sandbox_bridge import run_free_form

    # Narrow the allowed root to a sub-dir of tmp_path; the test then
    # creates the workdir as a SIBLING of that sub-dir.
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    monkeypatch.setenv("OPEN_EDIT_PROJECTS_ROOT", str(allowed))

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "edit_graph.db").touch()

    result = run_free_form(
        code="# ir_api_version: 0.1; libs: {}",
        workdir=outside,
        project_id="p1",
        parent_op_id="e1",
    )
    assert not result.success
    assert result.reason == "invalid_argument"
    # Critical: no .sandbox scratch dir was created in the rejected workdir.
    assert not (outside / ".sandbox").exists(), (
        "scratch dir was created in a rejected workdir — host-side "
        "staging happened before validation"
    )


def test_run_free_form_rejects_nonexistent_workdir(tmp_path):
    """P9: a workdir that doesn't exist (or has no edit_graph.db) is rejected."""
    from open_edit.agent.sandbox_bridge import run_free_form

    workdir = tmp_path / "does_not_exist"
    # don't create it
    result = run_free_form(
        code="# ir_api_version: 0.1; libs: {}",
        workdir=workdir,
        project_id="p1",
        parent_op_id="e1",
    )
    assert not result.success
    assert result.reason == "invalid_argument"


def test_run_render_rejects_workdir_outside_allowed_root(tmp_path, monkeypatch):
    """P9: run_render also validates workdir. A workdir outside the allowed
    root returns RenderResult(ok=False, detail='invalid_argument') and does
    NOT stage _render_code.py on the host.
    """
    from open_edit.agent.sandbox_bridge import run_render
    from open_edit.agent.exceptions import RenderResult

    allowed = tmp_path / "allowed"
    allowed.mkdir()
    monkeypatch.setenv("OPEN_EDIT_PROJECTS_ROOT", str(allowed))

    outside = tmp_path / "outside"
    outside.mkdir()
    output_path = outside / "out.mp4"

    result = run_render(
        code="pass",
        workdir=outside,
        output_path=output_path,
    )
    assert isinstance(result, RenderResult)
    assert result.ok is False
    assert result.detail == "invalid_argument"
    # No _render_code.py was written into the rejected workdir.
    assert not (outside / "_render_code.py").exists(), (
        "_render_code.py was written into a rejected workdir — host-side "
        "staging happened before validation"
    )


# =========================================================================
# 5a: top-level safety net must not echo repr(e) (which leaks absolute
# paths and exception args) back to the LLM.
# =========================================================================

def test_run_free_form_internal_error_does_not_leak_paths(tmp_path):
    """5a: a top-level exception in the run path must not include the
    absolute path / secret args of the original exception in result.detail.
    """
    from open_edit.agent.sandbox_bridge import run_free_form

    workdir = tmp_path / "proj"
    workdir.mkdir()
    (workdir / "edit_graph.db").touch()

    secret = "/this/path/should/never/leak/to/the/llm/abc123"

    def _raise(*a, **k):
        raise RuntimeError(f"database error at {secret}")

    with patch(
        "open_edit.agent.sandbox_bridge._resolve_sandbox_bin",
        side_effect=_raise,
    ):
        result = run_free_form(
            code="# ir_api_version: 0.1; libs: {}",
            workdir=workdir,
            project_id="p1",
            parent_op_id="e1",
        )

    assert not result.success
    assert result.reason == "internal_error"
    assert secret not in result.detail, (
        f"detail leaked secret path: {result.detail!r}"
    )
    # The exception class name is fine to surface (it tells the LLM what
    # kind of failure happened without leaking data).
    assert "RuntimeError" in result.detail


# =========================================================================
# 5b: child stderr/stdout in result.detail must be a single line with no
# control characters, bounded length. For render, the child stderr is NOT
# surfaced in detail at all (only a coarse reason).
# =========================================================================

def test_run_free_form_sandbox_error_stderr_sanitized(tmp_path):
    """5b: when the Rust binary returns ok=false with a multi-line,
    control-char-laden stderr, the wrapper's result detail is one line,
    no control chars, bounded length.
    """
    from open_edit.agent.sandbox_bridge import run_free_form

    workdir = tmp_path / "proj"
    workdir.mkdir()
    (workdir / "edit_graph.db").touch()

    long_stderr = "line1\nline2\nline3" + "\x00\x01\x02" + ("x" * 1000)
    mock_run = MagicMock(
        returncode=0,
        stdout=json.dumps({
            "ok": False,
            "reason": "sandbox_failed",
            "stderr": long_stderr,
        }) + "\n",
    )
    with patch(
        "open_edit.agent.sandbox_bridge.subprocess.run",
        return_value=mock_run,
    ):
        result = run_free_form(
            code="# ir_api_version: 0.1; libs: {}",
            workdir=workdir,
            project_id="p1",
            parent_op_id="e1",
        )

    assert not result.success
    assert result.reason == "sandbox_failed"
    detail = result.detail
    assert "\n" not in detail, f"detail has newlines: {detail!r}"
    assert "\r" not in detail, f"detail has CR: {detail!r}"
    assert "\x00" not in detail, f"detail has NUL: {detail!r}"
    assert len(detail) <= 300, f"detail too long ({len(detail)}): {detail!r}"


def test_run_render_stderr_not_in_detail(tmp_path):
    """5b: render sandbox stderr/stdout is logged server-side but NOT
    surfaced in result.detail — only a coarse reason.
    """
    from open_edit.agent.sandbox_bridge import run_render

    workdir = tmp_path / "proj"
    workdir.mkdir()
    (workdir / "edit_graph.db").touch()
    output_path = workdir / "out.mp4"

    fake_proc = MagicMock()
    fake_proc.returncode = 1
    fake_proc.stdout = "stdout-secret"
    fake_proc.stderr = "stderr-secret /etc/passwd token123"

    with patch(
        "open_edit.agent.sandbox_bridge._resolve_render_binary",
        return_value="/fake/binary",
    ), patch(
        "open_edit.agent.sandbox_bridge.subprocess.run",
        return_value=fake_proc,
    ):
        result = run_render(
            code="pass",
            workdir=workdir,
            output_path=output_path,
        )

    assert result.ok is False
    for needle in ("stderr-secret", "/etc/passwd", "token123", "stdout-secret"):
        assert needle not in result.detail, (
            f"detail leaked {needle!r}: {result.detail!r}"
        )


# =========================================================================
# 6a: scratch dir under workdir/.sandbox/run_<id> must be removed on
# success — otherwise each successful free-form run leaves ~3 staged files
# on disk forever.
# =========================================================================

@patch("open_edit.agent.sandbox_bridge._validate_ops_incrementally")
@patch("open_edit.agent.sandbox_bridge.subprocess.run")
def test_run_free_form_removes_scratch_dir_on_success(
    mock_run, mock_validate, tmp_path,
):
    """6a: scratch dir is removed on success."""
    from open_edit.agent.sandbox_bridge import run_free_form

    workdir = tmp_path / "proj"
    workdir.mkdir()
    (workdir / "edit_graph.db").touch()

    def _fake_run(cmd, **kwargs):
        ops_idx = cmd.index("--ops-output")
        ops_path = Path(cmd[ops_idx + 1])
        ops_path.parent.mkdir(parents=True, exist_ok=True)
        ops_path.write_text("{}\n")
        return MagicMock(
            returncode=0,
            stdout=json.dumps({"ok": True, "duration_s": 0.1}) + "\n",
        )

    mock_run.side_effect = _fake_run
    mock_validate.return_value = ([], None)

    result = run_free_form(
        code="# ir_api_version: 0.1; libs: {}",
        workdir=workdir,
        project_id="p1",
        parent_op_id="e1",
    )
    assert result.success, (
        f"expected success, got: {result.reason} {result.detail!r}"
    )

    sandbox_dir = workdir / ".sandbox"
    if sandbox_dir.exists():
        leftovers = list(sandbox_dir.iterdir())
        assert not leftovers, (
            f"scratch dir not cleaned on success: {leftovers}"
        )


@patch("open_edit.agent.sandbox_bridge.subprocess.run")
def test_run_free_form_passes_ops_output_to_sandbox(mock_run, tmp_path):
    """Regression (v1.2 release bug found during CLI demo):

    The bridge must pass `--ops-output <ops_path>` to the Rust sandbox binary.
    Without it, the binary fails with a usage error (missing required arg),
    the bridge gets no JSON on stdout, and `rust` is None — which crashes
    the protocol parser at `rust.get('ok')` with AttributeError.

    Introduced by v1.1 T6 cleanup pass (commit 0567448) which removed the
    flag from the bridge's subprocess call without providing a default in
    the Rust binary. The 5 free-form tests in test_free_form_e2e.py skip
    when bwrap is missing, so the regression was never caught locally.
    """
    from open_edit.agent.sandbox_bridge import run_free_form
    workdir = tmp_path / "proj"
    workdir.mkdir()
    (workdir / "edit_graph.db").touch()

    # Mock the binary to return a valid protocol JSON. The wrapper will then
    # try to read ops.jsonl (which doesn't exist) and return ops_missing —
    # but the cmd has already been captured by mock_run.call_args.
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout='{"exit_code":0,"ok":true,"stderr":""}\n',
    )
    run_free_form(
        code="# ir_api_version: 0.1; libs: {}",
        workdir=workdir,
        project_id="p1",
        parent_op_id="e1",
    )
    cmd = mock_run.call_args[0][0]
    assert "--ops-output" in cmd, (
        f"bridge must pass --ops-output to the sandbox binary; got cmd: {cmd}"
    )
    idx = cmd.index("--ops-output")
    ops_path_arg = cmd[idx + 1]
    # ops_path should be inside the workdir, ending with ops.jsonl
    assert ops_path_arg.endswith("ops.jsonl"), (
        f"expected ops.jsonl path, got {ops_path_arg}"
    )
    assert workdir.resolve() in Path(ops_path_arg).resolve().parents, (
        f"ops path should be under workdir {workdir}, got {ops_path_arg}"
    )


@patch("open_edit.agent.sandbox_bridge.subprocess.run")
def test_run_free_form_no_json_in_stdout_returns_protocol_error(mock_run, tmp_path):
    """Defense in depth: if the Rust binary exits without writing any
    JSON to stdout (e.g. a usage error from a missing required arg), the
    bridge must return sandbox_protocol_error with a clear message —
    NOT crash with AttributeError on `rust.get('ok')`.

    Companion to test_run_free_form_passes_ops_output_to_sandbox: even if a
    future bug removes the --ops-output flag again, the user gets a useful
    error instead of an internal_error with a stack trace.
    """
    from open_edit.agent.sandbox_bridge import run_free_form
    workdir = tmp_path / "proj"
    workdir.mkdir()
    (workdir / "edit_graph.db").touch()

    # Simulate the Rust binary failing with a usage error to stderr and
    # nothing on stdout (the exact shape we hit with the v1.2 release bug).
    mock_run.return_value = MagicMock(
        returncode=2,
        stdout="",
        stderr="error: the following required arguments were not provided:\n  --ops-output <OPS_OUTPUT>\n",
    )
    result = run_free_form(
        code="# ir_api_version: 0.1; libs: {}",
        workdir=workdir,
        project_id="p1",
        parent_op_id="e1",
    )
    assert not result.success
    assert result.reason == "sandbox_protocol_error", (
        f"expected sandbox_protocol_error, got {result.reason}: {result.detail}"
    )
    assert "no protocol JSON" in result.detail


# =========================================================================
# M1 (v1.1 polish): wrapper must parse protocol JSON even when stdout
# has print() noise. Defensive against the Rust binary emitting anything
# on stdout before the final JSON line. Without the fix, json.loads()
# raises JSONDecodeError and the wrapper returns sandbox_protocol_error.
# =========================================================================

@patch("open_edit.agent.sandbox_bridge.subprocess.run")
def test_free_form_print_does_not_corrupt_protocol_json(mock_run, tmp_path):
    """A free-form script's print() output must not corrupt the protocol JSON.

    Simulates a Rust binary whose stdout contains print() noise (e.g. from
    the script inside the sandbox leaking through, or from a transitional
    bug) before the final protocol JSON line. The wrapper must find and
    parse the JSON, not fail with sandbox_protocol_error.
    """
    from open_edit.agent.sandbox_bridge import run_free_form
    workdir = tmp_path / "proj"
    workdir.mkdir()
    (workdir / "edit_graph.db").touch()

    # The protocol JSON is the LAST line that starts with '{'.
    # Everything before it on the Rust binary's stdout is noise from the
    # script's print() calls (which is what M1 fixes in the Rust binary
    # by piping+discarding bwrap's child stdout).
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout='print("hello")\nprint("world")\n{"exit_code":0,"ok":true,"stderr":""}\n',
    )

    result = run_free_form(
        code="# ir_api_version: 0.1; libs: {}\nprint('hello')",
        workdir=workdir,
        project_id="p1",
        parent_op_id="e1",
    )

    # Without the fix: json.loads fails on noisy stdout -> sandbox_protocol_error.
    # With the fix: wrapper scans for the last '{' line and parses it.
    # After parsing, ops.jsonl is missing (no real bwrap run), so we get
    # ops_missing -- which proves the JSON parse succeeded.
    assert result.reason != "sandbox_protocol_error", (
        f"wrapper failed to parse noisy stdout: {result!r}"
    )


# =========================================================================
# I1 (final-fixes): run_render must return RenderResult, never raise.
# =========================================================================

def test_run_render_binary_missing_returns_failed_result(tmp_path):
    """I1: missing render binary → RenderResult(ok=False), no exception.

    Before the fix: run_render raised SandboxError (or FileNotFoundError
    via _resolve_render_binary). The brief's C7 contract says run_render
    must NEVER raise; it must return a structured RenderResult with
    ok=False and a detail string.
    """
    from open_edit.agent.sandbox_bridge import run_render
    from open_edit.agent.exceptions import RenderResult

    workdir = tmp_path / "proj"
    workdir.mkdir()
    (workdir / "edit_graph.db").touch()
    output_path = workdir / "out.mp4"

    # Force _resolve_render_binary to raise (no binary in any known location).
    with patch(
        "open_edit.agent.sandbox_bridge._resolve_render_binary",
        side_effect=FileNotFoundError("no render binary"),
    ):
        result = run_render(
            code="pass",
            workdir=workdir,
            output_path=output_path,
        )

    assert isinstance(result, RenderResult)
    assert result.ok is False
    assert "no render binary" in result.detail or "binary" in result.detail.lower()


def test_run_render_nonzero_exit_returns_failed_result(tmp_path):
    """I1: render binary exits non-zero → RenderResult(ok=False), no exception.

    5b: the raw child stderr is no longer surfaced in result.detail (it
    could contain internal paths, tokens, or prompt-injection payloads).
    The detail carries a coarse reason (the exit code) and the full
    stderr is logged server-side instead.
    """
    from open_edit.agent.sandbox_bridge import run_render
    from open_edit.agent.exceptions import RenderResult

    workdir = tmp_path / "proj"
    workdir.mkdir()
    (workdir / "edit_graph.db").touch()
    output_path = workdir / "out.mp4"

    fake_proc = MagicMock()
    fake_proc.returncode = 1
    fake_proc.stdout = ""
    fake_proc.stderr = "render crashed with internal stack trace"

    with patch(
        "open_edit.agent.sandbox_bridge._resolve_render_binary",
        return_value="/fake/binary",
    ), patch(
        "open_edit.agent.sandbox_bridge.subprocess.run",
        return_value=fake_proc,
    ):
        result = run_render(
            code="pass",
            workdir=workdir,
            output_path=output_path,
        )

    assert isinstance(result, RenderResult)
    assert result.ok is False
    # The detail carries the exit code (coarse reason) but NOT the raw stderr.
    assert "1" in result.detail  # exit code appears in the detail
    assert "render crashed" not in result.detail
    assert "stack trace" not in result.detail


def test_run_render_missing_output_returns_failed_result(tmp_path):
    """I1: render binary exits 0 but doesn't produce output → RenderResult(ok=False)."""
    from open_edit.agent.sandbox_bridge import run_render
    from open_edit.agent.exceptions import RenderResult

    workdir = tmp_path / "proj"
    workdir.mkdir()
    (workdir / "edit_graph.db").touch()
    output_path = workdir / "out.mp4"  # never created

    fake_proc = MagicMock()
    fake_proc.returncode = 0
    fake_proc.stdout = ""
    fake_proc.stderr = ""

    with patch(
        "open_edit.agent.sandbox_bridge._resolve_render_binary",
        return_value="/fake/binary",
    ), patch(
        "open_edit.agent.sandbox_bridge.subprocess.run",
        return_value=fake_proc,
    ):
        result = run_render(
            code="pass",
            workdir=workdir,
            output_path=output_path,
        )

    assert isinstance(result, RenderResult)
    assert result.ok is False
    assert str(output_path) in result.detail


def test_run_render_timeout_returns_failed_result(tmp_path):
    """I1: subprocess.TimeoutExpired → RenderResult(ok=False), no exception."""
    from open_edit.agent.sandbox_bridge import run_render
    from open_edit.agent.exceptions import RenderResult
    import subprocess as _subprocess

    workdir = tmp_path / "proj"
    workdir.mkdir()
    (workdir / "edit_graph.db").touch()
    output_path = workdir / "out.mp4"

    with patch(
        "open_edit.agent.sandbox_bridge._resolve_render_binary",
        return_value="/fake/binary",
    ), patch(
        "open_edit.agent.sandbox_bridge.subprocess.run",
        side_effect=_subprocess.TimeoutExpired(cmd="x", timeout=10),
    ):
        result = run_render(
            code="pass",
            workdir=workdir,
            output_path=output_path,
        )

    assert isinstance(result, RenderResult)
    assert result.ok is False
    assert "timed out" in result.detail.lower() or "timeout" in result.detail.lower()


def test_run_render_success_returns_ok_result(tmp_path):
    """I1: successful render → RenderResult(ok=True, path=output_path)."""
    from open_edit.agent.sandbox_bridge import run_render
    from open_edit.agent.exceptions import RenderResult

    workdir = tmp_path / "proj"
    workdir.mkdir()
    (workdir / "edit_graph.db").touch()
    output_path = workdir / "out.mp4"

    fake_proc = MagicMock()
    fake_proc.returncode = 0
    fake_proc.stdout = ""
    fake_proc.stderr = ""

    def _create_output(*args, **kwargs):
        output_path.write_bytes(b"fake")
        return fake_proc

    with patch(
        "open_edit.agent.sandbox_bridge._resolve_render_binary",
        return_value="/fake/binary",
    ), patch(
        "open_edit.agent.sandbox_bridge.subprocess.run",
        side_effect=_create_output,
    ):
        result = run_render(
            code="pass",
            workdir=workdir,
            output_path=output_path,
        )

    assert isinstance(result, RenderResult)
    assert result.ok is True
    assert result.path == output_path


# =========================================================================
# I2 (final-fixes): _validate_references must cover all 24 op types.
# =========================================================================

def _build_minimal_timeline(tmp_path):
    """Build a Project with one clip + one effect + one group for use in
    reference validation tests. Returns (project, timeline, edit_graph)."""
    from open_edit.ir.types import (
        AddClipOp, AddEffectOp, Asset, GroupEditsOp, Project, new_id,
    )
    from open_edit.ir.apply import derive_timeline
    from open_edit.storage.edit_graph import EditGraphStore

    workdir = tmp_path / "proj"
    workdir.mkdir()
    db_path = workdir / "edit_graph.db"
    EditGraphStore(db_path)  # creates the schema
    assets_dir = workdir / "assets"
    assets_dir.mkdir()

    a = Asset(
        asset_hash="asset_abc",
        original_path="x",
        stored_path="x",
        type="video",
    )
    assets = {"asset_abc": a}

    add_clip = AddClipOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        asset_hash="asset_abc", track_id="t1", position_sec=0.0,
        in_point_sec=0.0, out_point_sec=5.0,
    )
    add_effect = AddEffectOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        target_kind="clip", target_id=add_clip.clip_id,
        effect_type="blur", effect_id="effect_xyz",
    )
    group = GroupEditsOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        edit_ids=[add_clip.edit_id], label="group1",
    )

    edit_graph = [add_clip, add_effect, group]
    project = Project(
        project_id="p1", name="test",
        workdir=workdir, assets=assets, edit_graph=edit_graph,
    )
    timeline = derive_timeline(project)
    return project, timeline, edit_graph


def test_validate_references_missing_clip_op_raises(tmp_path):
    """I2: ops that reference a clip_id not in the project must raise."""
    from open_edit.ir.types import TrimClipOp, MoveClipOp, RemoveClipOp
    from open_edit.agent.sandbox_bridge import _validate_references
    from open_edit.ir.types import new_id

    _, timeline, edit_graph = _build_minimal_timeline(tmp_path)
    assets = {}

    for cls in (TrimClipOp, MoveClipOp, RemoveClipOp):
        if cls is MoveClipOp:
            op = cls(
                edit_id=new_id(), author="ai", parent_id="p1",
                clip_id="no_such_clip", new_track_id="t2", new_position_sec=1.0,
            )
        else:
            op = cls(
                edit_id=new_id(), author="ai", parent_id="p1",
                clip_id="no_such_clip",
                **({"new_in_point_sec": 0.0, "new_out_point_sec": 1.0} if cls is TrimClipOp else {}),
            )
        with pytest.raises(ReferenceError, match="clip_id"):
            _validate_references(op, timeline, assets, edit_graph)


def test_validate_references_slip_ripple_speed_split_ramp_raises(tmp_path):
    """I2: SlipClipOp, RippleDeleteClipOp, ChangeClipSpeedOp, SplitClipOp,
    SetClipSpeedRampOp must validate clip_id."""
    from open_edit.ir.types import (
        SlipClipOp, RippleDeleteClipOp, ChangeClipSpeedOp, SplitClipOp,
        SetClipSpeedRampOp, new_id,
    )
    from open_edit.agent.sandbox_bridge import _validate_references

    _, timeline, edit_graph = _build_minimal_timeline(tmp_path)
    assets = {}

    bad = {
        "slip": SlipClipOp(edit_id=new_id(), author="ai", parent_id="p1",
                            clip_id="nope", delta_sec=0.5),
        "ripple": RippleDeleteClipOp(edit_id=new_id(), author="ai", parent_id="p1",
                                      clip_id="nope"),
        "speed": ChangeClipSpeedOp(edit_id=new_id(), author="ai", parent_id="p1",
                                    clip_id="nope", rate=2.0),
        "split": SplitClipOp(edit_id=new_id(), author="ai", parent_id="p1",
                              clip_id="nope", at_sec=1.0),
        "ramp": SetClipSpeedRampOp(edit_id=new_id(), author="ai", parent_id="p1",
                                    clip_id="nope"),
    }
    for name, op in bad.items():
        with pytest.raises(ReferenceError, match="clip_id"):
            _validate_references(op, timeline, assets, edit_graph)


def test_validate_references_add_transition_missing_clip_raises(tmp_path):
    """I2: AddTransitionOp with missing clip_a_id or clip_b_id must raise."""
    from open_edit.ir.types import AddTransitionOp, new_id
    from open_edit.agent.sandbox_bridge import _validate_references

    _, timeline, edit_graph = _build_minimal_timeline(tmp_path)
    assets = {}

    op = AddTransitionOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        clip_a_id="nope_a", clip_b_id="nope_b",
        transition_type="luma", duration_sec=0.5,
    )
    with pytest.raises(ReferenceError, match="clip_a_id"):
        _validate_references(op, timeline, assets, edit_graph)


def test_validate_references_transition_ops_validate_id(tmp_path):
    """I2: RemoveTransitionOp + SetTransitionPropertyOp must validate transition_id.

    Transitions are stored as Effect on the clip. We test by giving a bogus id.
    """
    from open_edit.ir.types import (
        RemoveTransitionOp, SetTransitionPropertyOp, new_id,
    )
    from open_edit.agent.sandbox_bridge import _validate_references

    _, timeline, edit_graph = _build_minimal_timeline(tmp_path)
    assets = {}

    for cls in (RemoveTransitionOp, SetTransitionPropertyOp):
        kwargs = {"edit_id": new_id(), "author": "ai", "parent_id": "p1",
                  "transition_id": "no_such_transition"}
        if cls is SetTransitionPropertyOp:
            kwargs.update({"prop_name": "x", "value": "y"})
        op = cls(**kwargs)
        with pytest.raises(ReferenceError, match="transition_id"):
            _validate_references(op, timeline, assets, edit_graph)


def test_validate_references_remove_set_effect_validates_clip_index(tmp_path):
    """I2: RemoveEffectOp + SetEffectParamOp must validate clip_id and effect_index."""
    from open_edit.ir.types import RemoveEffectOp, SetEffectParamOp, new_id
    from open_edit.agent.sandbox_bridge import _validate_references

    _, timeline, edit_graph = _build_minimal_timeline(tmp_path)
    assets = {}

    # missing clip
    op_bad_clip = RemoveEffectOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        clip_id="nope", effect_index=0,
    )
    with pytest.raises(ReferenceError, match="clip_id"):
        _validate_references(op_bad_clip, timeline, assets, edit_graph)

    # valid clip but invalid index
    real_clip_id = timeline.tracks[0].clips[0].clip_id
    op_bad_idx = RemoveEffectOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        clip_id=real_clip_id, effect_index=999,
    )
    with pytest.raises(ReferenceError, match="effect_index"):
        _validate_references(op_bad_idx, timeline, assets, edit_graph)

    # SetEffectParamOp: bad param name
    op_bad_param = SetEffectParamOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        clip_id=real_clip_id, effect_index=0,
        param_name="nonexistent_param", value="1",
    )
    with pytest.raises(ReferenceError, match="param_name"):
        _validate_references(op_bad_param, timeline, assets, edit_graph)


def test_validate_references_remove_keyframe_validates(tmp_path):
    """I2: RemoveKeyframeOp must validate effect_id, param, and frame."""
    from open_edit.ir.types import RemoveKeyframeOp, new_id
    from open_edit.agent.sandbox_bridge import _validate_references

    _, timeline, edit_graph = _build_minimal_timeline(tmp_path)
    assets = {}

    # missing effect_id
    op_bad_eff = RemoveKeyframeOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        effect_id="nope", param="gain", frame=1.0,
    )
    with pytest.raises(ReferenceError, match="effect_id"):
        _validate_references(op_bad_eff, timeline, assets, edit_graph)


def test_validate_references_replace_clip_source_validates(tmp_path):
    """I2: ReplaceClipSourceOp must validate clip_id AND new_asset_hash."""
    from open_edit.ir.types import ReplaceClipSourceOp, new_id
    from open_edit.agent.sandbox_bridge import _validate_references

    _, timeline, edit_graph = _build_minimal_timeline(tmp_path)
    assets = {"asset_abc": type("A", (), {"asset_hash": "asset_abc"})()}

    # bad clip
    op_bad_clip = ReplaceClipSourceOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        clip_id="nope", new_asset_hash="asset_abc",
    )
    with pytest.raises(ReferenceError, match="clip_id"):
        _validate_references(op_bad_clip, timeline, assets, edit_graph)

    real_clip_id = timeline.tracks[0].clips[0].clip_id
    # bad asset
    op_bad_asset = ReplaceClipSourceOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        clip_id=real_clip_id, new_asset_hash="not_in_project",
    )
    with pytest.raises(ReferenceError, match="asset_hash"):
        _validate_references(op_bad_asset, timeline, assets, edit_graph)


def test_validate_references_normalize_audio_validates_target(tmp_path):
    """I2: NormalizeAudioOp must validate target_id (clip or track)."""
    from open_edit.ir.types import NormalizeAudioOp, new_id
    from open_edit.agent.sandbox_bridge import _validate_references

    _, timeline, edit_graph = _build_minimal_timeline(tmp_path)
    assets = {}

    # clip with bad id
    op_bad_clip = NormalizeAudioOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        target_kind="clip", target_id="nope", target_dbfs=-16.0,
    )
    with pytest.raises(ReferenceError, match="target_id"):
        _validate_references(op_bad_clip, timeline, assets, edit_graph)

    # track with bad id
    op_bad_track = NormalizeAudioOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        target_kind="track", target_id="nope", target_dbfs=-16.0,
    )
    with pytest.raises(ReferenceError, match="target_id"):
        _validate_references(op_bad_track, timeline, assets, edit_graph)

    # unknown kind
    op_bad_kind = NormalizeAudioOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        target_kind="project", target_id="nope", target_dbfs=-16.0,
    )
    with pytest.raises(ReferenceError, match="target_kind"):
        _validate_references(op_bad_kind, timeline, assets, edit_graph)


def test_validate_references_group_ungroup_validates(tmp_path):
    """I2: GroupEditsOp + UngroupEditsOp must validate."""
    from open_edit.ir.types import GroupEditsOp, UngroupEditsOp, new_id
    from open_edit.agent.sandbox_bridge import _validate_references

    _, timeline, edit_graph = _build_minimal_timeline(tmp_path)
    assets = {}

    # group with non-existent edit_id
    op_bad_edit = GroupEditsOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        edit_ids=["no_such_edit"], label="g1",
    )
    with pytest.raises(ReferenceError, match="edit_id"):
        _validate_references(op_bad_edit, timeline, assets, edit_graph)

    # ungroup with non-existent label
    op_bad_label = UngroupEditsOp(
        edit_id=new_id(), author="ai", parent_id="p1", label="no_such_group",
    )
    with pytest.raises(ReferenceError, match="label"):
        _validate_references(op_bad_label, timeline, assets, edit_graph)


def test_validate_references_raw_mlt_and_free_form_skip(tmp_path):
    """I2: RawMltXmlOp and FreeFormCodeOp need no reference check."""
    from open_edit.ir.types import RawMltXmlOp, FreeFormCodeOp, new_id
    from open_edit.agent.sandbox_bridge import _validate_references

    _, timeline, edit_graph = _build_minimal_timeline(tmp_path)
    assets = {}

    op_raw = RawMltXmlOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        xml="<mlt/>", description="x",
    )
    op_free = FreeFormCodeOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        code="pass",
    )
    # Should not raise ReferenceError; they only trigger the parent_id check
    # (which both pass). The catch is the lack of op-level reference check.
    # We use a dummy parent_id to avoid the parent_id check.
    op_raw.parent_id = "p1"
    op_free.parent_id = "p1"
    # No reference error means validation passed.
    _validate_references(op_raw, timeline, assets, edit_graph)
    _validate_references(op_free, timeline, assets, edit_graph)
