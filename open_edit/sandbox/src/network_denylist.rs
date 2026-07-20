// Phase 3 Task 5: stub. Real implementation in Task 6.
use libseccomp::{ScmpAction, ScmpFilterContext};

pub fn install(_ctx: &mut ScmpFilterContext) -> anyhow::Result<()> {
    // Placeholder: no seccomp filtering yet. Task 6 implements the
    // SCMP_ACT_ERRNO(EPERM) denylist for socket/connect/bind/accept/listen/
    // sendto/recvfrom/sendmsg/recvmsg.
    Ok(())
}
