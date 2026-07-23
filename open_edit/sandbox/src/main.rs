// Phase 3 Task 5: main entry. CLI parsing + JSON output.
// Task 6 adds seccomp/rlimits/timeout. Task 7 adds the actual bwrap invocation.

use clap::Parser;
use serde::Serialize;
use std::process::{ExitCode, Stdio};

mod jail;
mod network_denylist;
mod nproc;

#[derive(Parser, Debug)]
#[command(name = "open-edit-sandbox", about = "Free-form Python sandbox")]
struct Cli {
    /// rw directory for ops.jsonl + temps
    #[arg(long)]
    scratch: String,

    /// ro directory of source media (repeatable, 0+)
    #[arg(long = "source-ro", value_name = "PATH")]
    source_ro: Vec<String>,

    /// ro file (edit_graph.db)
    #[arg(long = "project-meta")]
    project_meta: Option<String>,

    /// Python binary to invoke inside the sandbox
    #[arg(long = "python-bin")]
    python_bin: String,

    /// major.minor, e.g. "3.14"; child parses back to tuple
    #[arg(long = "expected-py-version")]
    expected_py_version: String,

    /// wall-clock timeout in seconds
    #[arg(long, default_value_t = 30)]
    timeout: u64,

    /// RLIMIT_CPU in seconds
    #[arg(long, default_value_t = 30)]
    cpu: u64,

    /// RLIMIT_AS in MB
    #[arg(long, default_value_t = 2048)]
    mem: u64,

    /// machine-readable JSON output
    #[arg(long)]
    json: bool,
}

#[derive(Serialize)]
struct Output {
    ok: bool,
    exit_code: i32,
    reason: String,
    duration_s: f64,
    stderr: String,
}

fn main() -> ExitCode {
    let cli = Cli::parse();

    // Task 7: real bwrap invocation via jail::run_bwrap_with_limits.
    let limits = jail::Limits {
        mem_mb: cli.mem,
        cpu_secs: cli.cpu,
        ..Default::default()
    };
    let bwrap_args = build_bwrap_args(&cli);
    let mut cmd = std::process::Command::new("bwrap");
    // M1 (v1.1): pipe the bwrap child so the script's print() calls and
    // the IR ops JSONL (which the bootstrap writes to a file) cannot leak
    // into this Rust process's stdout. Without piping, bwrap inherits our
    // stdout, and any print() in the script mixes with the protocol JSON
    // we print below, causing sandbox_protocol_error on the Python side.
    cmd.args(&bwrap_args)
        .stdout(Stdio::piped())   // capture child stdout (script noise + IR ops JSONL)
        .stderr(Stdio::piped());  // capture child stderr (warnings, tracebacks)
    let started = std::time::Instant::now();
    let result = jail::run_bwrap_with_limits(cmd, limits, cli.timeout);
    let duration_s = started.elapsed().as_secs_f64();

    // Decode the captured child streams. child_stdout is DISCARDED -- it's
    // script noise (user print() calls) and the IR ops JSONL, which is
    // also written to /scratch/ops.jsonl inside the sandbox and read by
    // the Python wrapper after the run. child_stderr is the script's
    // stderr (warnings, tracebacks) and is surfaced to the Python wrapper
    // via Output.stderr for debugging.
    let (child_stdout, child_stderr) = match &result {
        Ok(r) => {
            let so = String::from_utf8_lossy(&r.stdout).to_string();
            let se = String::from_utf8_lossy(&r.stderr).to_string();
            (so, se)
        }
        Err(_) => (String::new(), String::new()),
    };
    let _ = child_stdout;  // explicitly unused; documented above

    let output = match result {
        Ok(r) if r.status.success() => Output {
            ok: true,
            exit_code: r.status.code().unwrap_or(0),
            reason: String::new(),
            duration_s,
            stderr: child_stderr,
        },
        Ok(r) if r.timed_out => Output {
            ok: false,
            exit_code: -1,
            reason: "timeout".to_string(),
            duration_s,
            stderr: child_stderr,
        },
        Ok(r) => Output {
            ok: false,
            exit_code: r.status.code().unwrap_or(1),
            reason: "nonzero_exit".to_string(),
            duration_s,
            stderr: child_stderr,
        },
        Err(e) => Output {
            ok: false,
            exit_code: -1,
            reason: "setup_error".to_string(),
            duration_s,
            stderr: format!("{e:#}"),
        },
    };

    println!("{}", serde_json::to_string(&output).unwrap());
    if output.ok { ExitCode::SUCCESS } else { ExitCode::from(1) }
}

fn build_bwrap_args(cli: &Cli) -> Vec<String> {
    let mut args: Vec<String> = vec![];

    // Namespaces: fail loud, no -try.
    args.push("--unshare-user".into());
    args.push("--unshare-pid".into());
    args.push("--unshare-ipc".into());
    args.push("--unshare-net".into());
    args.push("--die-with-parent".into());

    // Read-only filesystem bindings.
    args.push("--ro-bind".into()); args.push("/usr".into()); args.push("/usr".into());
    args.push("--ro-bind".into()); args.push("/lib".into());  args.push("/lib".into());
    args.push("--ro-bind-try".into()); args.push("/lib64".into()); args.push("/lib64".into());
    args.push("--ro-bind".into()); args.push("/etc".into());  args.push("/etc".into());
    args.push("--symlink".into()); args.push("/usr/bin".into());  args.push("/bin".into());
    args.push("--symlink".into()); args.push("/usr/sbin".into()); args.push("/sbin".into());
    args.push("--proc".into()); args.push("/proc".into());

    // Source media: ro-bound, one --source-ro per directory.
    for (i, src) in cli.source_ro.iter().enumerate() {
        args.push("--ro-bind".into());
        args.push(src.clone());
        args.push(format!("/mnt/src{i}"));
    }

    // Project metadata: ro-bound.
    if let Some(meta) = &cli.project_meta {
        args.push("--ro-bind".into());
        args.push(meta.clone());
        args.push("/mnt/meta".into());
    }

    // Scratch dir: rw.
    args.push("--bind".into());
    args.push(cli.scratch.clone());
    args.push("/scratch".into());

    // Tmpfs mounts.
    args.push("--tmpfs".into()); args.push("/tmp".into());
    args.push("--tmpfs".into()); args.push("/home".into());
    args.push("--tmpfs".into()); args.push("/var".into());

    // Single --dev /dev (C4).
    args.push("--dev".into()); args.push("/dev".into());

    // Env (M3).
    args.push("--setenv".into()); args.push("HOME".into()); args.push("/tmp".into());
    args.push("--setenv".into()); args.push("XDG_CACHE_HOME".into()); args.push("/tmp/cache".into());

    // Make the Python venv (and its site-packages, e.g. pydantic) reachable.
    // The host venv lives under /home, which we mount as an empty tmpfs below,
    // so we recreate its ancestor dirs as empty and ro-bind ONLY the venv
    // itself. This lets `<venv>/bin/python` (a symlink to /usr/bin/python3,
    // already bound) resolve without exposing the rest of /home.
    add_venv_binds(&mut args, &cli.python_bin);

    args.push("--new-session".into());

    // The Python invocation: version check, then exec _bootstrap.py then code.py.
    // C5: parse the major.minor string back to a tuple in the child.
    let py_check = format!(
        "import sys; expected = tuple(int(x) for x in '{ver}'.split('.')); assert sys.version_info[:2] == expected, 'sandbox Python mismatch'; g = {{'__name__': '__main__'}}; exec(open('/scratch/_bootstrap.py').read(), g); exec(open('/scratch/code.py').read(), g)",
        ver = cli.expected_py_version,
    );
    args.push("--".into());
    args.push(cli.python_bin.clone());
    args.push("-c".into());
    args.push(py_check);
    args
}

/// Recreate the venv directory inside the namespace so the interpreter and its
/// site-packages are resolvable, without exposing the rest of `/home`.
///
/// `python_bin` is typically `<venv>/bin/python`. We ro-bind `<venv>` at its
/// real path and materialize its (otherwise-empty) ancestor directories so the
/// symlink `<venv>/bin/python -> /usr/bin/python3` resolves to the already
/// bound system interpreter. System interpreters under `/usr` need no action.
fn add_venv_binds(args: &mut Vec<String>, python_bin: &str) {
    let pb = std::path::Path::new(python_bin);
    let Some(bin_dir) = pb.parent() else { return; };
    let Some(venv) = bin_dir.parent() else { return; };
    if !venv.starts_with("/home") {
        return;
    }
    // Collect ancestor directories between /home (exclusive) and the venv
    // (exclusive), shallowest first, and materialize them as empty dirs.
    let mut parts: Vec<&std::path::Path> = Vec::new();
    let mut cur = venv.parent();
    while let Some(p) = cur {
        if p == std::path::Path::new("/home") {
            break;
        }
        parts.push(p);
        cur = p.parent();
    }
    parts.reverse();
    for d in parts {
        args.push("--dir".into());
        args.push(d.to_string_lossy().into_owned());
    }
    let venv_s = venv.to_string_lossy().into_owned();
    args.push("--ro-bind".into());
    args.push(venv_s.clone());
    args.push(venv_s);
}
