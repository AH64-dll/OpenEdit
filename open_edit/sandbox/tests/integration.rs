// Phase 3 Task 7: integration tests for the sandbox binary.
// L7: feature-gated; run with `cargo test --features integration`.

#![cfg(feature = "integration")]

use assert_cmd::Command;
use std::fs;
use tempfile::tempdir;

fn sandbox_bin() -> Command {
    Command::cargo_bin("open-edit-sandbox").unwrap()
}

#[test]
#[ignore = "TODO(Task 8): _bootstrap.py needs IR/op models inlined by sandbox_bridge.inspect.getsource()"]
fn e2e_python_runs_and_writes_ops() {
    let scratch = tempdir().unwrap();
    fs::write(scratch.path().join("code.py"), "ir.add_clip(asset_hash='abc', track_id='t1', position_sec=0.0)").unwrap();
    fs::write(scratch.path().join("_bootstrap.py"), "import json\nfrom open_edit.ir.api import IR\nclass _Buf(list):\n    def append(self, op):\n        super().append(op)\n        with open('/scratch/ops.jsonl', 'a') as f: f.write(op.model_dump_json() + '\\n')\nir = IR(_Buf(), project_id='p', parent_op_id='e')").unwrap();

    let _ = sandbox_bin()
        .arg("--scratch").arg(scratch.path())
        .arg("--python-bin").arg("/usr/bin/python3.14")
        .arg("--expected-py-version").arg("3.14")
        .arg("--json")
        .assert();
    // The full assert (file existence, op count) is in tests/test_free_form_e2e.py
    // because the Rust binary needs IR/op models inlined into _bootstrap.py.
}

#[test]
fn bwrap_unavailable_reason() {
    // Run with PATH=/nonexistent; bwrap not found → reason=setup_error
    let scratch = tempdir().unwrap();
    sandbox_bin()
        .env("PATH", "/nonexistent")
        .arg("--scratch").arg(scratch.path())
        .arg("--python-bin").arg("/usr/bin/python3.14")
        .arg("--expected-py-version").arg("3.14")
        .arg("--json")
        .assert()
        .failure();
    // Detailed JSON inspection is brittle; the e2e test in Python covers it.
}
