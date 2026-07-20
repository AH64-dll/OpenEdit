#!/usr/bin/env bash
# Setup the cgroup v2 directory for the open_edit render sandbox.
# Idempotent: safe to re-run.
# Requires: cgroup v2 mounted at /sys/fs/cgroup/, root or sudo.

set -euo pipefail

CGROUP_DIR="/sys/fs/cgroup/open_edit_render"
PARENT_SUBSYS="/sys/fs/cgroup/cgroup.subtree_control"

# 1. Verify cgroup v2
if [[ "$(stat -fc %T /sys/fs/cgroup 2>/dev/null)" != "cgroup2fs" ]]; then
    echo "ERROR: cgroup v2 not mounted at /sys/fs/cgroup/" >&2
    echo "  This system uses cgroup v1 or has no cgroup support." >&2
    echo "  Render sandbox resource limits will not apply." >&2
    exit 1
fi

# 2. Check for "no internal processes" constraint (cgroup v2 forbids enabling
#    a new controller if the parent has processes that don't use it).
if grep -q "populated 1" /sys/fs/cgroup/cgroup.events 2>/dev/null; then
    echo "WARNING: Root cgroup has live processes; enabling new controllers may fail." >&2
    echo "  Workaround: move processes to a child cgroup before re-running." >&2
fi

# 3. Create the cgroup directory (idempotent via mkdir -p)
mkdir -p "$CGROUP_DIR"

# 4. Enable memory + cpu controllers on the PARENT (not the child) so they're
#    available to open_edit_render.
#    Idempotent: skip if already enabled.
if ! grep -q "memory cpu" "$PARENT_SUBSYS" 2>/dev/null; then
    echo "+memory +cpu" > "$PARENT_SUBSYS" || {
        echo "ERROR: Failed to enable memory/cpu controllers on root cgroup." >&2
        echo "  This usually means the root cgroup has live processes." >&2
        echo "  Workaround: move them to a child cgroup, or run on a fresh system." >&2
        exit 1
    }
fi

# 5. Grant current user ownership (resets on reboot; re-run after each boot)
if [[ -n "${SUDO_USER:-}" ]]; then
    chown -R "$SUDO_USER" "$CGROUP_DIR"
elif [[ "$(id -u)" == "0" && -n "${USER:-}" ]]; then
    chown -R "$USER" "$CGROUP_DIR"
fi

echo "OK: cgroup ready at $CGROUP_DIR"
echo "  Memory max: $(cat "$CGROUP_DIR/memory.max" 2>/dev/null || echo 'unlimited')"
echo "  CPU max:    $(cat "$CGROUP_DIR/cpu.max" 2>/dev/null || echo 'unlimited')"
