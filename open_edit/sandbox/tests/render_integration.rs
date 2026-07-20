//! Phase 4.5 W2: render sandbox integration test.
//! Feature-gated; run with `cargo test --features integration -- --ignored`.

use assert_cmd::Command;

#[test]
#[ignore = "requires bwrap + writable /sys/fs/cgroup"]
fn render_sandbox_runs_python_writes_output() {
    let tmp = tempfile::tempdir().unwrap();
    let code = tmp.path().join("script.py");
    std::fs::write(&code, "import os; open(os.environ['OUTPUT_PATH'], 'w').write('rendered')").unwrap();
    let output = tmp.path().join("out.txt");
    Command::cargo_bin("open-edit-render-sandbox")
        .unwrap()
        .arg("--code").arg(&code)
        .arg("--workdir").arg(tmp.path())
        .arg("--output").arg(&output)
        .arg("--timeout").arg("30")
        .arg("--mem").arg("512")
        .timeout(std::time::Duration::from_secs(60))
        .assert()
        .success();
    assert!(output.exists());
    assert_eq!(std::fs::read_to_string(&output).unwrap(), "rendered");
}
