//! open-edit-render-sandbox: heavy-compute sandbox for motion graphics generation.
//!
//! Per phase4-design-revised.md §4.3 (W2): two-sandbox design.
//! Trust posture: NO seccomp (this sandbox is for trusted user-initiated
//! work, not adversarial free-form code). cgroup enforces memory + CPU.
//! `--with-hwaccel` allows /dev/dri for GPU work.

use anyhow::{Context, Result};
use clap::Parser;
use std::os::unix::process::CommandExt;
use std::path::PathBuf;
use std::process::Command;

mod render_jail;

#[derive(Parser, Debug)]
#[command(name = "open-edit-render-sandbox")]
struct Args {
    /// Path to Python source file to execute.
    #[arg(long)]
    code: PathBuf,

    /// Workdir to bind (read-write).
    #[arg(long)]
    workdir: PathBuf,

    /// Output asset path (file the Python code writes to).
    #[arg(long)]
    output: PathBuf,

    /// Wall-clock timeout in seconds.
    #[arg(long, default_value = "3600")]
    timeout: u64,

    /// Memory limit in MB.
    #[arg(long, default_value = "4096")]
    mem: u64,

    /// Allow /dev/dri/* and /dev/shm for GPU work.
    #[arg(long, default_value = "false")]
    with_hwaccel: bool,
}

fn main() -> Result<()> {
    let args = Args::parse();
    let limits = render_jail::Limits {
        mem_mb: args.mem,
        cpu_secs: args.timeout,
        nofile: 4096,
        nproc: 4096,
    };

    // Translate the user-supplied code/output paths to in-sandbox paths.
    // The workdir is bound to /workdir inside the sandbox (rebind, not bind-
    // to-self, because --tmpfs /tmp would otherwise wipe the host path).
    let in_sandbox_code = in_sandbox_path(&args.code, &args.workdir, "/workdir")?;
    let in_sandbox_output = in_sandbox_path(&args.output, &args.workdir, "/workdir")?;

    let mut cmd = build_bwrap_cmd(&args, &in_sandbox_code, &in_sandbox_output);
    // Set cgroup + rlimit in pre_exec
    unsafe {
        cmd.pre_exec(move || -> std::io::Result<()> {
            render_jail::apply_cgroup_limits(&limits)
                .map_err(|e| std::io::Error::other(format!("cgroup: {e:#}")))?;
            render_jail::apply_rlimits(&limits)
                .map_err(|e| std::io::Error::other(format!("rlimit: {e:#}")))?;
            Ok(())
        });
    }

    let output_result = cmd.output().context("failed to spawn bwrap")?;
    if !output_result.status.success() {
        anyhow::bail!(
            "render sandbox exited with code {:?}: {}",
            output_result.status.code(),
            String::from_utf8_lossy(&output_result.stderr)
        );
    }
    Ok(())
}

/// Translate an absolute host path into the in-sandbox path. Both `path` and
/// `workdir` must be absolute; `path` must live under `workdir` (the only
/// directory bound into the sandbox).
fn in_sandbox_path(path: &PathBuf, workdir: &PathBuf, mount: &str) -> Result<PathBuf> {
    if !path.is_absolute() {
        anyhow::bail!("path must be absolute: {path:?}");
    }
    if !workdir.is_absolute() {
        anyhow::bail!("workdir must be absolute: {workdir:?}");
    }
    let rel = path.strip_prefix(workdir)
        .with_context(|| format!("{path:?} is not under workdir {workdir:?}"))?;
    Ok(PathBuf::from(mount).join(rel))
}

fn build_bwrap_cmd(args: &Args, in_sandbox_code: &PathBuf, in_sandbox_output: &PathBuf) -> Command {
    let mut cmd = Command::new("bwrap");
    cmd.arg("--unshare-user")
        .arg("--unshare-pid")
        .arg("--unshare-ipc")
        .arg("--unshare-net")
        .arg("--ro-bind").arg("/usr").arg("/usr")
        .arg("--ro-bind-try").arg("/lib64").arg("/lib64")
        .arg("--ro-bind").arg("/etc").arg("/etc")
        .arg("--symlink").arg("/usr/bin").arg("/bin")
        .arg("--symlink").arg("/usr/sbin").arg("/sbin")
        .arg("--bind").arg(&args.workdir).arg("/workdir")
        .arg("--tmpfs").arg("/tmp")
        .arg("--tmpfs").arg("/home")
        .arg("--dev").arg("/dev")
        .arg("--setenv").arg("HOME").arg("/tmp")
        .arg("--setenv").arg("OUTPUT_PATH").arg(in_sandbox_output)
        .arg("--setenv").arg("PYTHONUNBUFFERED").arg("1")
        .arg("--new-session")
        .arg("--");
    if args.with_hwaccel {
        cmd.arg("--bind").arg("/dev/dri").arg("/dev/dri")
            .arg("--bind").arg("/dev/shm").arg("/dev/shm");
    }
    cmd.arg("python3").arg(in_sandbox_code);
    cmd
}
