//! Render sandbox jail: cgroup + rlimit resource limits, no seccomp.

use std::path::Path;

use anyhow::{Context, Result};

pub struct Limits {
    pub mem_mb: u64,
    pub cpu_secs: u64,
    pub nofile: u64,
    pub nproc: u64,
}

const DEFAULT_CGROUP_DIR: &str = "/sys/fs/cgroup/open_edit_render";

pub fn apply_cgroup_limits(limits: &Limits) -> Result<()> {
    apply_cgroup_limits_at(limits, Path::new(DEFAULT_CGROUP_DIR))
}

/// Write the three cgroup control files (`memory.max`, `cpu.max`,
/// `cgroup.procs`) under `cgroup_dir`. Returns an error (and prints a
/// stderr warning) if any write fails — previously these were silently
/// swallowed via `let _ = ...`, which meant the render sandbox's
/// documented MemoryMax=4G + CPUQuota=300% limits were never actually
/// applied in environments where the cgroup dir was missing.
pub(crate) fn apply_cgroup_limits_at(limits: &Limits, cgroup_dir: &Path) -> Result<()> {
    let memory_max = format!("{}M", limits.mem_mb);
    if let Err(e) = std::fs::write(
        cgroup_dir.join("memory.max"),
        memory_max.as_bytes(),
    ) {
        eprintln!(
            "warning: cgroup memory.max write to {} failed: {e}",
            cgroup_dir.display(),
        );
        return Err(e).with_context(|| {
            format!(
                "cgroup memory.max write to {} failed",
                cgroup_dir.display(),
            )
        });
    }

    let cpu_quota = (limits.cpu_secs * 10000).min(300000);
    if let Err(e) = std::fs::write(
        cgroup_dir.join("cpu.max"),
        format!("{} 100000", cpu_quota),
    ) {
        eprintln!(
            "warning: cgroup cpu.max write to {} failed: {e}",
            cgroup_dir.display(),
        );
        return Err(e).with_context(|| {
            format!(
                "cgroup cpu.max write to {} failed",
                cgroup_dir.display(),
            )
        });
    }

    if let Err(e) = std::fs::write(
        cgroup_dir.join("cgroup.procs"),
        format!("{}", std::process::id()),
    ) {
        eprintln!(
            "warning: cgroup cgroup.procs write to {} failed: {e}",
            cgroup_dir.display(),
        );
        return Err(e).with_context(|| {
            format!(
                "cgroup cgroup.procs write to {} failed",
                cgroup_dir.display(),
            )
        });
    }

    Ok(())
}

pub fn apply_rlimits(limits: &Limits) -> Result<()> {
    use nix::sys::resource::{setrlimit, Resource};
    setrlimit(Resource::RLIMIT_AS, limits.mem_mb * 1024 * 1024, limits.mem_mb * 1024 * 1024)?;
    setrlimit(Resource::RLIMIT_NOFILE, limits.nofile, limits.nofile)?;
    setrlimit(Resource::RLIMIT_NPROC, limits.nproc, limits.nproc)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_limits() -> Limits {
        Limits {
            mem_mb: 100,
            cpu_secs: 30,
            nofile: 1024,
            nproc: 1024,
        }
    }

    #[test]
    fn apply_cgroup_limits_returns_error_for_nonexistent_default_dir() {
        // I3 (final-fixes): the render sandbox's documented MemoryMax=4G
        // and CPUQuota=300% limits must actually be applied, OR the
        // function must return an error so the operator can see it.
        // The old `let _ =` swallow returned Ok(()) even when the
        // cgroup dir didn't exist on the host.
        let limits = test_limits();
        // Skip if the test environment happens to have the cgroup dir
        // (e.g., a special CI setup). The default path is application-
        // specific so this is a sane skip.
        if Path::new(DEFAULT_CGROUP_DIR).exists() {
            eprintln!("skipping: {DEFAULT_CGROUP_DIR} exists");
            return;
        }
        let result = apply_cgroup_limits(&limits);
        let err = result.expect_err(
            "expected error for missing cgroup dir, got Ok (the old \
             `let _ =` swallow bug is back)",
        );
        let msg = format!("{err:#}");
        assert!(
            msg.contains("memory.max") || msg.contains("cgroup"),
            "error message should reference the cgroup path, got: {msg}",
        );
    }

    #[test]
    fn apply_cgroup_limits_at_returns_error_for_nonexistent_path() {
        // I3 (final-fixes): testable seam for the error path.
        let tmp = tempfile::tempdir().unwrap();
        let bogus = tmp.path().join("does_not_exist");
        let result = apply_cgroup_limits_at(&test_limits(), &bogus);
        let err = result.expect_err(
            "expected error for missing cgroup dir, got Ok (the old \
             `let _ =` swallow bug is back)",
        );
        let msg = format!("{err:#}");
        assert!(
            msg.contains("memory.max") || msg.contains("cgroup"),
            "error message should reference the cgroup path, got: {msg}",
        );
    }

    #[test]
    fn apply_cgroup_limits_at_writes_three_files_when_dir_exists() {
        // Sanity: when the cgroup dir exists, all three writes must
        // succeed (this is the happy path the render binary depends on).
        let tmp = tempfile::tempdir().unwrap();
        apply_cgroup_limits_at(&test_limits(), tmp.path())
            .expect("writes should succeed when cgroup dir exists");
        let mem = std::fs::read_to_string(tmp.path().join("memory.max"))
            .unwrap();
        assert_eq!(mem, "100M");
        let cpu = std::fs::read_to_string(tmp.path().join("cpu.max"))
            .unwrap();
        assert!(
            cpu.ends_with(" 100000"),
            "cpu.max should end with the period, got: {cpu}",
        );
        let procs =
            std::fs::read_to_string(tmp.path().join("cgroup.procs"))
                .unwrap();
        assert!(
            !procs.trim().is_empty(),
            "cgroup.procs should contain our pid",
        );
    }
}
