# Phase 0 — fixture, reload behavior, "Untitled" diff: DEFERRED (needs human)

Three of Phase 0's six remaining tasks are GUI-dependent and were **not**
executed by the agent. They are listed here in the exact form the spec
asks for, with the specific command the human should run and what to
record. None of them block Phase 1.

---

## Task 4 — Build a ground-truth `.kdenlive` fixture

**Why deferred:** This is the single most important Phase 0 deliverable,
and it requires a human in front of the actual Kdenlive window. The
spec says explicitly: *"a real project a real human made, not something
PyAgent invented."* A scripted fixture would defeat the purpose.

**What to do:**

1. Open Kdenlive (`kdenlive` — already verified to launch on this
   machine, see `versions.txt`).
2. Project → New (or File → New, depending on theme).
3. Project Bin → Add Clip → import at least 2 short clips. The
   `testdata/clip_short.mp4` from `mlt-pipeline` is fine; any short
   `.mp4` works.
4. Drag both clips onto the timeline (different tracks if you want to
   exercise multi-track).
5. Trim at least one clip's in/out points.
6. Add a transition between the two clips (a `dissolve` is fine, even
   though the spec notes some transition params are under-documented —
   that gap is itself useful evidence).
7. Add a title clip (Titles → Add Title).
8. Add at least one marker / guide on the timeline ruler.
9. File → Save As…
   `pyagent-kdenlive-guide/spike-results/fixtures/manual_baseline.kdenlive`
10. Quit Kdenlive cleanly.

**What to record in this file** (after saving):

```text
Saved at: YYYY-MM-DD HH:MM
File size: <bytes>
Number of producers: <grep -c '<producer ' fixture.kdenlive>
Number of playlists: <grep -c '<playlist ' fixture.kdenlive>
Number of kdenlive: properties: <grep -c 'kdenlive:' fixture.kdenlive>
Document version: <grep 'kdenlive:docproperties.version' fixture.kdenlive>
Title-clip marker count: <grep -c '<marker' fixture.kdenlive>
```

This file becomes Phase 2's ground truth — its round-trip tests will
load it, mutate one specific field, save it, diff the output against
the input, and assert the diff is exactly the intended field plus
expected benign noise (e.g., whitespace, attribute reordering by
`lxml`).

---

## Task 5 — External-edit reload behavior

**Why deferred:** Requires a human to perform the Kdenlive+editor+save
dance. Cannot be done headlessly on this machine.

**What to do, after the fixture is saved and Kdenlive is still open
with it loaded:**

1. With `manual_baseline.kdenlive` open in Kdenlive, open the same
   file in a text editor (do **not** use the editor's auto-reload).
2. Tweak a marker's comment text, e.g. change `hello` → `hello world`.
   Save the file in the text editor.
3. Switch back to Kdenlive. Observe.

**Record exactly one of:**

- `(a) Silent auto-reload` — Kdenlive's timeline/monitor updates
  without any prompt. (If so, note whether markers update or only
  clips/structure.)
- `(b) Reload prompt` — Kdenlive shows a dialog asking to reload.
  Quote the dialog's exact wording.
- `(c) Manual reload required` — Kdenlive ignores the change
  silently until the user does File → Reopen (or similar). Note the
  exact menu path.
- `(d) Locked / blocks re-edit` — Kdenlive refuses to save over the
  externally-modified file without explicit user action.

**What to write in this file:**

```text
Observed: <(a) | (b) | (c) | (d)>
Dialog text (if any): <verbatim>
Reload path (if required): <menu path>
Markers updated on auto-reload? <yes/no/n/a>
Tested on: YYYY-MM-DD HH:MM
```

Phase 5 of the guide is built entirely around whichever answer this
is. The result feeds back into the design choice between
*"edit-and-reload"* and *"edit-and-save-then-trigger-reload-via-D-Bus"*.

---

## Task 6 — "Untitled" diff between `project.mlt` and `manual_baseline.kdenlive`

**Why partially deferred:** The `project.mlt` half is ready (already
produced by `mlt-pipeline` at `projects/test-run/project.mlt`). The
`manual_baseline.kdenlive` half is the file the human will save in
Task 4 above. Once both files exist, the diff is one command:

```sh
diff -u \
  /home/ah64/apps/mlt-pipeline/projects/test-run/project.mlt \
  /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide/spike-results/fixtures/manual_baseline.kdenlive \
  | head -200 \
  > /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide/spike-results/mlt_vs_kdenlive_diff.txt
```

**What to record in this file:**

- The header lines of each file (first 30 lines) side by side.
- The set of `kdenlive:`-namespaced properties present in the
  `.kdenlive` file but absent in the bare `.mlt`. This is the
  minimum-set checklist for Phase 2's writer to emit a file that
  Kdenlive recognises as a real project (i.e., not "Untitled").
- The `kdenlive:docproperties.version` value (currently `1.1` in
  25.12 / 26.x).

**Quick pre-check (runnable now, without the human's fixture):**

```sh
# What does the bare .mlt have that looks "kdenlive-ish"?
grep -c 'kdenlive:' /home/ah64/apps/mlt-pipeline/projects/test-run/project.mlt
# Expected: 0  (this is exactly the "Untitled" problem the guide
#               promises to fix in Phase 2)

# What's the .mlt's first 30 lines?
head -30 /home/ah64/apps/mlt-pipeline/projects/test-run/project.mlt
```

The pre-check already proves the claim: the Go pipeline emits zero
`kdenlive:` properties, so the file has no project name, no
docversion, and no bin metadata — exactly the conditions under which
Kdenlive labels it "Untitled." Phase 2's job is to fix that.
