# Phase 0 — Spike & Validate

## Context (recap — read `01_FINDINGS_AND_ARCHITECTURE.md` for full detail)

We're building PyAgent, a Python AI agent with a chat UI that edits Kdenlive
projects. Kdenlive has no plugin API or scripting console, so the plan is:
(A) a file-based engine that reads/writes `.kdenlive` XML directly — no risk,
fully buildable — plus (C) a possible upgrade to a community Kdenlive fork
(`D-Ogi/kdenlive`) that adds a real D-Bus scripting API, if it turns out to
build and work cleanly.

**This phase produces no product code.** It produces facts, written down,
that every later phase depends on. Do not skip it and do not guess at any of
these answers — every one is cheap to check directly.

## Goal

Answer six concrete questions on the actual EndeavourOS machine this will run
on, and save the evidence (command output, sample files) into a
`spike-results/` folder so later phases can reference it instead of
re-deriving it.

## Tasks

- [ ] **Environment baseline.** Run `kdenlive --version` and confirm it's a
      25.x / KF6 build. Run `melt --version` and `ffprobe -version` (already
      dependencies of `mlt-pipeline`, confirm they're the same ones). Save
      output to `spike-results/versions.txt`.

- [ ] **Locate MLT's YAML metadata locally.** Search for the MLT data
      directory (something like `find / -xdev -iname "*.yml" -path "*mlt*" 2>/dev/null`,
      or check `melt -query modules` / `melt -query filters` for a path hint).
      If found, copy a handful of sample `.yml` files into
      `spike-results/mlt-yml-samples/`. If not found locally, note that
      Phase 1 will need to pull them from `github.com/mltframework/mlt`
      instead — not a blocker either way, just determines Phase 1's source.

- [ ] **Check MLT Python bindings availability.**
      `pacman -Ss mlt-python-bindings` and `pacman -Ss python-mlt` (also
      check the AUR if nothing in official repos). If found and installable,
      install it and confirm `python3 -c "import mlt; print(mlt.__file__)"`
      works. Write the result (available/not, exact package name, whether
      import succeeds) to `spike-results/mlt-python-bindings.md`. This
      determines whether Phase 2 uses the bindings or plain `lxml`.

- [ ] **Build a ground-truth `.kdenlive` fixture.** In the actual Kdenlive
      GUI: new project → import 2 short clips (reuse `testdata/clip_short.mp4`
      from `mlt-pipeline` if convenient, or any two short test clips) → place
      both on the timeline → add one transition between them → add one title
      clip → add one marker → save as `spike-results/fixtures/manual_baseline.kdenlive`.
      This file is the ground truth Phase 2's round-trip tests get checked
      against — a real project a real human made, not something PyAgent
      invented, so if Phase 2 can open it, tweak it, and save it back without
      losing anything, you know the engine is trustworthy.

- [ ] **Test external-edit reload behavior.** With `manual_baseline.kdenlive`
      open in Kdenlive, edit an unimportant property directly in a text
      editor (e.g. tweak a marker's comment text) and save. Switch back to
      Kdenlive. Record exactly what happens: nothing / a reload prompt /
      silent reload / needs manual File→Open again. Write the observed
      behavior to `spike-results/reload_behavior.md` — Phase 5 is built
      entirely around whatever you find here, so be precise (screenshot or
      exact wording of any dialog that appears).

- [ ] **Confirm the "Untitled" issue and its fix.** Take the `project.mlt`
      your existing `mlt-pipeline` produces (run `./edit.sh` against a small
      test folder if you don't have one handy) and open it in Kdenlive.
      Confirm it opens as "Untitled" as your own docs note. Then take
      `manual_baseline.kdenlive` from above and confirm it opens with its
      real name. Diff the two files' headers side by side
      (`spike-results/mlt_vs_kdenlive_diff.txt`) — this becomes Phase 2's
      checklist of exactly which `kdenlive:`-namespaced properties are the
      minimum needed to stop being "Untitled."

- [ ] **Time-boxed D-Bus fork spike (max half a day).** Clone
      `github.com/D-Ogi/kdenlive`, follow its `dev-docs/build.md`, attempt a
      build with `-DUSE_DBUS=ON`. Stop at the half-day mark regardless of
      outcome. If it builds: launch it, and with `qdbus` or `busctl --user`
      introspect the running instance to find the *actual* D-Bus interface
      name (resolve the `org.kde.kdenlive.MainWindow` vs
      `org.kde.kdenlive.scripting` discrepancy noted in the findings doc) and
      call two or three of the simplest documented methods by hand. Record
      pass/fail and any errors verbatim in `spike-results/dbus_fork_spike.md`.
      If it fails to build: record the actual error, don't just mark it
      "failed" — a missing dependency is a very different result from a
      genuine incompatibility, and Phase 7 will want to know which.

## Explicit non-goals for this phase

- Don't write any of PyAgent's actual code yet.
- Don't spend more than half a day on the D-Bus fork spike task specifically —
  if it's not building by then, stop, record why, and move on. Phase 7
  revisits it later with more time if Phases 0–6 go well.
- Don't try to fix or work around whatever reload behavior you find in the
  fifth task — just document it accurately. Phase 5 decides what to do about it.

## Acceptance criteria

- [ ] `spike-results/` folder exists with: `versions.txt`,
      `mlt-yml-samples/` (or a note that none were found locally),
      `mlt-python-bindings.md`, `fixtures/manual_baseline.kdenlive`,
      `reload_behavior.md`, `mlt_vs_kdenlive_diff.txt`, `dbus_fork_spike.md`.
- [ ] Every file above contains an actual observed result, not a prediction —
      if you didn't run the command, the answer isn't in here yet.
- [ ] You can state, in one sentence each, the answers to: "does Kdenlive
      auto-reload changed files," "is the D-Bus fork buildable here," and
      "which `kdenlive:` properties are the minimum for a real project name."

## Handoff to Phase 1

Phase 1 needs `mlt-yml-samples/` (or the "pull from GitHub instead" decision)
and will reuse `manual_baseline.kdenlive` as one of its worked examples.
