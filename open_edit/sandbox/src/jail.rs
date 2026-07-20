// Phase 3 Task 6: seccomp + rlimits + fork+watcher timeout.
use std::os::unix::process::CommandExt;
use std::process::Command;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Duration;

use anyhow::Context;
use nix::sys::resource::{Resource, setrlimit};
use nix::sys::signal::{self, Signal};
use nix::unistd::Pid;

use crate::network_denylist;

pub struct RunResult {
    pub status: std::process::ExitStatus,
    pub timed_out: bool,
}

pub struct Limits {
    pub mem_mb: u64,
    pub cpu_secs: u64,
    pub nofile: u64,
    pub nproc: u64,
}

impl Default for Limits {
    fn default() -> Self {
        // nproc default raised from 64 to 1024: in real Linux desktop
        // environments a single user routinely has 100+ processes, and
        // 64 caused "Creating new namespace failed: Resource temporarily
        // unavailable" before bwrap could even start. 1024 still prevents
        // trivial fork bombs while leaving headroom for normal use.
        Self { mem_mb: 2048, cpu_secs: 30, nofile: 256, nproc: 1024 }
    }
}

fn seccomp_to_io(label: &str) -> impl Fn(libseccomp::error::SeccompError) -> std::io::Error + '_ {
    move |e| std::io::Error::other(format!("{label}: {e}"))
}

/// Run `cmd` with seccomp network denylist, rlimits, and a wall-clock
/// timeout enforced by a watcher thread.
///
/// The seccomp filter is built and loaded inside `pre_exec` (after fork,
/// before exec in the single-threaded child) so the parent's syscall
/// surface is untouched. Loading a BPF filter requires the child to be
/// single-threaded, which the `pre_exec` contract guarantees.
pub fn run_bwrap_with_limits(
    mut cmd: Command,
    limits: Limits,
    timeout_secs: u64,
) -> anyhow::Result<RunResult> {
    // SAFETY: pre_exec runs between fork() and exec() in the child. The
    // child is single-threaded at this point. We set rlimits, then build
    // and load a seccomp filter that denies network syscalls. After this
    // returns, the child execs the new program with the seccomp filter
    // active.
    unsafe {
        cmd.pre_exec(move || -> std::io::Result<()> {
            let bytes = limits.mem_mb.saturating_mul(1024 * 1024);
            setrlimit(Resource::RLIMIT_AS, bytes, bytes)
                .map_err(|e| std::io::Error::other(format!("setrlimit RLIMIT_AS: {e}")))?;
            setrlimit(Resource::RLIMIT_CPU, limits.cpu_secs, limits.cpu_secs)
                .map_err(|e| std::io::Error::other(format!("setrlimit RLIMIT_CPU: {e}")))?;
            setrlimit(Resource::RLIMIT_NOFILE, limits.nofile, limits.nofile)
                .map_err(|e| std::io::Error::other(format!("setrlimit RLIMIT_NOFILE: {e}")))?;
            setrlimit(Resource::RLIMIT_NPROC, limits.nproc, limits.nproc)
                .map_err(|e| std::io::Error::other(format!("setrlimit RLIMIT_NPROC: {e}")))?;

            let mut ctx = libseccomp::ScmpFilterContext::new_filter(
                libseccomp::ScmpAction::Allow,
            )
            .map_err(seccomp_to_io("seccomp init"))?;
            network_denylist::install(&mut ctx)
                .map_err(|e| std::io::Error::other(format!("seccomp rules: {e:#}")))?;
            ctx.load().map_err(seccomp_to_io("seccomp load"))?;
            Ok(())
        });
    }

    let mut child = cmd.spawn().context("spawn bwrap")?;
    let pid = child.id() as i32;

    // Watcher thread: kill the child if it runs too long.
    let timed_out = Arc::new(AtomicBool::new(false));
    let to_clone = timed_out.clone();
    let watcher = std::thread::spawn(move || {
        std::thread::sleep(Duration::from_secs(timeout_secs));
        to_clone.store(true, Ordering::SeqCst);
        let _ = signal::kill(Pid::from_raw(pid), Signal::SIGTERM);
        std::thread::sleep(Duration::from_secs(2));
        let _ = signal::kill(Pid::from_raw(pid), Signal::SIGKILL);
    });

    let status = child.wait().context("wait bwrap")?;
    let timed_out_value = timed_out.load(Ordering::SeqCst);
    // Don't join the watcher; let it die naturally after the kill (no-op).
    drop(watcher);

    Ok(RunResult { status, timed_out: timed_out_value })
}

/// Backwards-compatible wrapper that routes through `run_bwrap_with_limits`
/// with the default limits. Task 7 switched callers over to the
/// `run_bwrap_with_limits` entry point with explicit limits from the CLI;
/// retained for external callers and tests.
#[allow(dead_code)]
pub fn run_bwrap(args: &[String], timeout_secs: u64) -> anyhow::Result<RunResult> {
    let mut cmd = Command::new("bwrap");
    cmd.args(args);
    run_bwrap_with_limits(cmd, Limits::default(), timeout_secs)
}
