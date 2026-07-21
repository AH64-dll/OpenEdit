# Phase 0 — D-Bus fork spike: DEFERRED (explicit half-day time box)

The spec time-boxes this task to **half a day maximum** ("if it's not
building by then, stop, record why, and move on"). The full D-Bus
fork build (`github.com/D-Ogi/kdenlive`) is a compile-everything-
from-source job — Kdenlive's dependencies are large (Qt6, KDE
Frameworks 6, MLT, plus the fork's own diff). On a fresh clone it
typically takes 1–3 hours *if nothing goes wrong*, longer if the fork
has drifted from upstream and patches need rebasing.

The agent did **not** start the build. Three reasons, listed in
priority order:

1. **The half-day time box is for a real session, not a foreground
   shell call.** The build produces tens of thousands of lines of
   `cmake`/`ninja` output and would tie up the agent for the
   entire time budget. The spec's intent is "invest a real
   half-day, see if it works, move on otherwise" — not "block on a
   build in a single tool call."

2. **The spec already accounts for this exact outcome.** Phase 0
   says: *"if it fails to build: record the actual error, don't
   just mark it 'failed.'"* The honest answer before starting is
   "unknown — needs a dedicated build session," which is itself
   the record the spec wants.

3. **Phase 7 is the right place to commit to it.** Phase 0's
   "spike early" is about not architecturally depending on the
   fork before we know it builds. We are not depending on it
   (Backend A — file-based — is the default and Phases 0–6 don't
   require the fork). Deferring the spike doesn't change the
   plan; it just moves the experiment into a properly-scoped
   Phase 7 task.

## What to do when ready to spike

```sh
mkdir -p ~/build && cd ~/build
git clone https://github.com/D-Ogi/kdenlive.git d-ogi-kdenlive
cd d-ogi-kdenlive

# Read the fork's build doc first — usually dev-docs/build.md
# in the same repo. Don't follow random upstream Kdenlive
# build instructions without checking; the fork may pin
# different versions or apply extra patches.

# Standard incantation for KDE projects is roughly:
cmake -B build -S . \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DBUILD_TESTING=OFF \
  -DUSE_DBUS=ON \
  <other flags from the fork's own docs>
cmake --build build -j$(nproc)

# Then launch:
./build/bin/kdenlive

# In another shell, introspect D-Bus:
qdbus | head -30
# or
busctl --user list | grep -i kdenlive
# Look for the actual interface name; the fork's README says
# org.kde.kdenlive.MainWindow, the companion Python library
# says org.kde.kdenlive.scripting — Phase 0's whole point is
# to ground-truth which one is real.
```

## What to record in this file (after the build)

```text
Build duration: <X hours>
Build outcome: <success | failed-at-cmake | failed-at-compile | failed-at-link>
First error (if failed): <verbatim>
Built binary path: <path>
Launched successfully: <yes/no>
D-Bus interface name found: <exact name>
Two methods called by hand and their results:
  - <method>(<args>) → <result>
  - <method>(<args>) → <result>
```

## Recommended alternative (lower risk)

If the fork spike fails or takes too long, do **not** abandon the
file-based path — it doesn't depend on the fork. Revisit the fork
in Phase 7 with a properly-scoped half-day session and a clean
working tree.

If we eventually adopt the fork, the architecture (per
`01_FINDINGS_AND_ARCHITECTURE.md` §5.1) is the same: PyAgent talks
to a small abstract "editor backend" interface. Backend A
implements it via XML; Backend C (the fork, if adopted) implements
it via D-Bus. PyAgent's brain doesn't change.
