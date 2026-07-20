// Phase 3 Task 5: stub. Real implementation in Tasks 6-7.
use std::process::Command;

pub struct RunResult {
    pub status: std::process::ExitStatus,
    pub timed_out: bool,
}

pub fn run_bwrap(_args: &[String], _timeout_secs: u64) -> anyhow::Result<RunResult> {
    // Placeholder. Task 6: add rlimits + fork+watcher timeout.
    // Task 7: add seccomp + bwrap invocation.
    //
    // For now, just exec bwrap with the args (no seccomp, no rlimits, no
    // timeout). This lets the binary be built and tested end-to-end before
    // the isolation layers are added.
    let mut cmd = Command::new("bwrap");
    cmd.args(_args);
    let status = cmd.status()?;
    Ok(RunResult { status, timed_out: false })
}
