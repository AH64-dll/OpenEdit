// Phase 3 Task 6: SCMP_ACT_ERRNO(EPERM) denylist for network syscalls.
use anyhow::Context;
use libseccomp::{ScmpAction, ScmpFilterContext, ScmpSyscall};

const DENIED_SYSCALLS: &[&str] = &[
    "socket", "connect", "bind", "accept", "listen",
    "sendto", "recvfrom", "sendmsg", "recvmsg",
];

/// Install a network-deny seccomp filter on `ctx`. Each denied syscall
/// returns EPERM (errno 1) instead of being killed, so the child sees
/// `PermissionError` from Python's socket module and can handle it.
pub fn install(ctx: &mut ScmpFilterContext) -> anyhow::Result<()> {
    let action = ScmpAction::Errno(1);
    for name in DENIED_SYSCALLS {
        let nr = ScmpSyscall::from_name(name)
            .with_context(|| format!("unknown syscall {name}"))?;
        ctx.add_rule_exact(action, nr)
            .with_context(|| format!("add_rule({name})"))?;
    }
    Ok(())
}
