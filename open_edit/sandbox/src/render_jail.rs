//! Render sandbox jail: cgroup + rlimit resource limits, no seccomp.

use anyhow::Result;

pub struct Limits {
    pub mem_mb: u64,
    pub cpu_secs: u64,
    pub nofile: u64,
    pub nproc: u64,
}

pub fn apply_cgroup_limits(limits: &Limits) -> Result<()> {
    // Best-effort cgroup setup. If cgroup v2 is not available, silently skip.
    // The Python code is responsible for self-limiting via mem_mb.
    let memory_max = format!("{}M", limits.mem_mb);
    let _ = std::fs::write(
        "/sys/fs/cgroup/open_edit_render/memory.max",
        memory_max.as_bytes(),
    );
    let _ = std::fs::write(
        "/sys/fs/cgroup/open_edit_render/cpu.max",
        format!("{} 100000", (limits.cpu_secs * 10000).min(300000)),
    );
    let _ = std::fs::write(
        "/sys/fs/cgroup/open_edit_render/cgroup.procs",
        format!("{}", std::process::id()),
    );
    Ok(())
}

pub fn apply_rlimits(limits: &Limits) -> Result<()> {
    use nix::sys::resource::{setrlimit, Resource};
    setrlimit(Resource::RLIMIT_AS, limits.mem_mb * 1024 * 1024, limits.mem_mb * 1024 * 1024)?;
    setrlimit(Resource::RLIMIT_NOFILE, limits.nofile, limits.nofile)?;
    setrlimit(Resource::RLIMIT_NPROC, limits.nproc, limits.nproc)?;
    Ok(())
}
