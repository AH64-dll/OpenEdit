//! Network isolation for the free-form sandbox.
//!
//! We block creation of IPv4/IPv6 sockets (socket()/socketpair() with family
//! AF_INET/AF_INET6) so the sandboxed code cannot open external network
//! connections. Other families are intentionally allowed:
//!   * AF_UNIX   — local IPC used by Python's stdlib (tempfile,
//!                 multiprocessing, importlib, ...). Blocking it breaks
//!                 normal execution.
//!   * AF_NETLINK — required by bubblewrap ITSELF to bring up the `lo`
//!                 loopback interface inside the unshared network namespace.
//!                 The previous denylist blocked `socket` wholesale, which
//!                 made bwrap fail with "loopback: Failed to look up lo"
//!                 and killed the sandbox.
//!
//! The sandbox therefore keeps its own network namespace AND seccomp
//! enforcement, with no loss of external-network isolation. Blocking
//! socket *creation* by family is sufficient: without an inet socket there
//! is nothing for connect/bind/etc. to act on, so we no longer need to
//! deny those syscalls (which would also have hit AF_UNIX).

use anyhow::Context;
use libseccomp::{ScmpAction, ScmpArgCompare, ScmpCompareOp, ScmpFilterContext, ScmpSyscall};

const AF_INET: u64 = 2;
const AF_INET6: u64 = 10;

/// Install a network-deny seccomp filter on `ctx`: creating an IPv4 or IPv6
/// socket returns EPERM, while AF_UNIX/AF_NETLINK and all other syscalls are
/// allowed.
pub fn install(ctx: &mut ScmpFilterContext) -> anyhow::Result<()> {
    let action = ScmpAction::Errno(1);
    for &family in &[AF_INET, AF_INET6] {
        for &syscall in &["socket", "socketpair"] {
            let nr = ScmpSyscall::from_name(syscall)
                .with_context(|| format!("unknown syscall {syscall}"))?;
            let cmp = ScmpArgCompare::new(0, ScmpCompareOp::Equal, family);
            ctx.add_rule_conditional(action, nr, &[cmp])
                .map_err(|e| anyhow::anyhow!("add_rule_conditional({syscall}): {e}"))?;
        }
    }
    Ok(())
}
