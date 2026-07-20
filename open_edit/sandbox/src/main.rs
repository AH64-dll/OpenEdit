// Phase 3 Task 5: main entry. CLI parsing + JSON output.
// Task 6 adds seccomp/rlimits/timeout. Task 7 adds the actual bwrap invocation.

use anyhow::Context;
use clap::Parser;
use serde::Serialize;
use std::process::ExitCode;

mod jail;
mod network_denylist;

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

    /// path of ops.jsonl (for sandbox_bridge to read after)
    #[arg(long = "ops-output")]
    ops_output: String,

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

    // Build the bwrap argv. Task 7 fills this in.
    let bwrap_args = build_bwrap_args(&cli);

    let started = std::time::Instant::now();
    let result = jail::run_bwrap(&bwrap_args, cli.timeout);
    let duration_s = started.elapsed().as_secs_f64();

    let output = match result {
        Ok(r) if r.status.success() => Output {
            ok: true,
            exit_code: r.status.code().unwrap_or(0),
            reason: String::new(),
            duration_s,
            stderr: String::new(),
        },
        Ok(r) if r.timed_out => Output {
            ok: false,
            exit_code: -1,
            reason: "timeout".to_string(),
            duration_s,
            stderr: String::new(),
        },
        Ok(r) => Output {
            ok: false,
            exit_code: r.status.code().unwrap_or(1),
            reason: "nonzero_exit".to_string(),
            duration_s,
            stderr: String::new(),
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
    // Task 7: full bwrap invocation. For now, just pass --version to verify
    // the binary works end-to-end.
    let mut args = vec!["--version".to_string()];
    // Placate the unused-variable warning until Task 7 fills this in.
    let _ = (&cli.scratch, &cli.source_ro, &cli.project_meta,
            &cli.python_bin, &cli.expected_py_version,
            &cli.ops_output);
    args
}
