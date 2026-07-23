//! Compute a safe RLIMIT_NPROC ceiling for the sandbox.
//!
//! A hard-coded absolute cap (e.g. 1024) fails with EAGAIN on hosts where
//! the current user already runs at least that many processes. That makes
//! bwrap's namespace-creation fork fail with:
//!   "Creating new namespace failed: Resource temporarily unavailable"
//! which is exactly the symptom that left the free-form sandbox dead.
//!
//! We instead set the limit to the current UID process count plus a fixed
//! headroom. This bounds a fork bomb to `baseline + HEADROOM` while never
//! dropping below the host's existing process count, so legitimate
//! namespace setup (which only needs a few forks) always succeeds.

use nix::unistd::getuid;

/// Extra processes the sandbox may spawn beyond the current baseline.
/// A fork bomb is therefore bounded to `baseline + HEADROOM`.
///
/// NOTE: bubblewrap forks heavily while setting up its user namespace, so
/// this headroom must be large enough to clear bwrap's own needs (observed
/// to require a ceiling of roughly 2048 on a normal desktop even with only
/// ~120 existing UID processes). 8192 leaves comfortable margin while still
/// capping a runaway fork bomb at `baseline + 8192`.
const FORK_BOMB_HEADROOM: u64 = 8192;

/// Count processes owned by the current real UID by scanning /proc.
/// Returns 0 if the scan fails for any reason (caller adds headroom).
pub fn current_user_process_count() -> u64 {
    let uid = getuid().as_raw();
    let mut count: u64 = 0;
    if let Ok(entries) = std::fs::read_dir("/proc") {
        for entry in entries.flatten() {
            let name = entry.file_name();
            let name = name.to_string_lossy();
            if !name.bytes().all(|b| b.is_ascii_digit()) {
                continue;
            }
            if let Ok(status) = std::fs::read_to_string(entry.path().join("status")) {
                for line in status.lines() {
                    if let Some(rest) = line.strip_prefix("Uid:") {
                        // Uid: <real> <effective> <saved> <filesystem>
                        if let Some(real) = rest.split_whitespace().next() {
                            if real.parse::<u32>().ok() == Some(uid) {
                                count += 1;
                            }
                        }
                        break;
                    }
                }
            }
        }
    }
    count
}

/// RLIMIT_NPROC ceiling for a given baseline = baseline + headroom.
pub fn relative_nproc_limit_with(base: u64) -> u64 {
    base.saturating_add(FORK_BOMB_HEADROOM)
}

/// RLIMIT_NPROC ceiling = current UID process count + headroom.
pub fn relative_nproc_limit() -> u64 {
    relative_nproc_limit_with(current_user_process_count())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn count_includes_self() {
        // The current process must be counted for its own UID.
        assert!(current_user_process_count() >= 1);
    }

    #[test]
    fn relative_limit_is_baseline_plus_headroom() {
        // Use a single baseline read so the assertion is race-free.
        let base = current_user_process_count();
        assert_eq!(relative_nproc_limit_with(base), base.saturating_add(FORK_BOMB_HEADROOM));
    }
}
