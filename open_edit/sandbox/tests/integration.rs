// Phase 3 Task 5: integration test scaffold. Real tests in Task 7.
//
// These tests are skipped unless the `integration` feature is enabled
// (`cargo test --features integration`). Task 7 replaces the bodies with
// real sandbox-execution assertions.

#![cfg(feature = "integration")]

use assert_cmd::Command;
use predicates::prelude::*;

#[test]
fn binary_runs_and_reports_json() {
    let mut cmd = Command::cargo_bin("open-edit-sandbox").unwrap();
    cmd.arg("--scratch")
        .arg("/tmp")
        .arg("--python-bin")
        .arg("/usr/bin/python3")
        .arg("--expected-py-version")
        .arg("3.14")
        .arg("--ops-output")
        .arg("/tmp/ops.jsonl")
        .arg("--json");
    cmd.assert()
        .success()
        .stdout(predicate::str::contains("\"ok\""));
}
