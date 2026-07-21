# External-edit reload behavior — observed

**Test method:** Kdenlive was running (PID 2046260) with the
`manual_baseline.kdenlive` fixture open. We introspected it over D-Bus
(`busctl --user`), edited the on-disk file with `sed`, then asked
Kdenlive for state via D-Bus properties — no human observation needed
for the state checks. The single thing a human needed to do (initial
fixture build) is done.

## Setup state captured

```
$ busctl --user get-property org.kde.kdenlive-2046260 /kdenlive/MainWindow_1 \
    org.qtproject.Qt.QWidget windowTitle
s "manual_baseline [*]/ 624x356 30.00fps"

$ busctl --user get-property org.kde.kdenlive-2046260 /kdenlive/MainWindow_1 \
    org.qtproject.Qt.QWidget windowFilePath
s ""
```

**Two things already surprising:**
1. `windowFilePath` is **empty** — even though Kdenlive has the file
   open. Qt/KDE normally populates this from `QWidget::windowFilePath`,
   which the `Kdenlive::Document` is supposed to set. Empty here means
   the document-level association is not propagating to the top-level
   window, which is itself a clue: Kdenlive isn't treating the loaded
   project as a "file I'm watching."
2. The title shows `[*]` even though we hadn't edited anything in
   Kdenlive yet. The project was just saved; `[*]` means "document
   modified relative to disk," which on a freshly-loaded freshly-saved
   project should be `false`. So either Kdenlive's title is stale, or
   some default-project property always counts as dirty. Not a blocker
   for Phase 5, just an observation.

## Test 1 — Edit on disk, no D-Bus call

```sh
sed -i 's/<property name="kdenlive:clipname">Sequence 1<\/property>/<property name="kdenlive:clipname">Sequence 1 PROOF<\/property>/' manual_baseline.kdenlive
sleep 1
busctl --user get-property org.kde.kdenlive-2046260 /kdenlive/MainWindow_1 \
  org.qtproject.Qt.QWidget windowTitle
# → s "manual_baseline [*]/ 624x356 30.00fps"  (unchanged)
```

**Result:** Kdenlive's title did **not** change. There is no auto-reload
of externally-edited files. No notification, no log, no signal.

## Test 2 — Call `file_revert` over D-Bus

```sh
busctl --user call org.kde.kdenlive-2046260 /kdenlive/MainWindow_1 \
  org.kde.KMainWindow activateAction s "file_revert"
# → b true   (call succeeded)
sleep 2
busctl --user get-property org.kde.kdenlive-2046260 /kdenlive/MainWindow_1 \
  org.qtproject.Qt.QWidget windowTitle
# → s "manual_baseline [*]/ 624x356 30.00fps"  (still unchanged)
```

**Result:** `file_revert` returns `true`, but it's the wrong action for
this purpose. The action's tooltip (queried via `actionToolTip s
"file_revert"`) is:

> "Revert unsaved changes made to document"

It reverts *in-memory timeline edits* to the last-loaded state, **not
"reload the file from disk."** For a project that has no in-memory
edits, the action is a no-op — which is exactly what we observed.

## Test 3 — Available reload-class actions

```sh
$ busctl --user call org.kde.kdenlive-2046260 /kdenlive/MainWindow_1 \
    org.kde.KMainWindow actions \
  | tr ' ' '\n' | grep -iE 'reload|revert|file_'
"reload_clip"   # relocates a missing bin clip to a new path; not file-reload
"file_revert"   # what we just tried; not file-reload
"file_open"     # opens a file picker
"file_open_recent"
"file_save_copy"
"file_save"
"file_new"
"file_quit"
```

**None of the actions is "re-open the current file from disk."** The
only ways to get Kdenlive to reflect an on-disk change are:

1. `file_open` → opens a dialog (we'd have to inject the path).
2. `file_open_recent` → may work, but the path would have to be in the
   recent-list.
3. Quit + relaunch with the file as the CLI argument.
4. `addProjectClip` + manual re-add (only adds, doesn't refresh).

## Verdict (one sentence)

**Kdenlive does not auto-reload externally-edited files; `file_revert`
is the wrong tool; the only working reload path is to close+reopen
the project, which on upstream 26.04 has to go through `file_open`
(prompt) or a full process relaunch.**

## Implications for Phase 5 (sync_and_reload)

The guide's "edit-and-reload" model needs to become
"edit-and-force-reload." Concretely, the cleanest options are:

1. **`file_open` with key-press injection** — call
   `activateAction("file_open")`, then `xdotool type <path>` + `Enter`.
   Fragile (needs a key-injection tool the spec doesn't assume; phase 8
   `kwin-mcp` territory). **Not recommended.**

2. **DBus call with path argument via a non-existent `openFile(url)`
   method** — Kdenlive 26.04's `MainWindow` interface does *not* expose
   this. Checked: no method matching `open*File*` or `loadProject`.

3. **Quit + relaunch with file argument** — actually the simplest and
   most reliable. From a script: `qdbus ... exitApp` (or `kill` with
   `SIGTERM`), then `kdenlive /path/to/file.kdenlive &` in a
   `disown`'d subshell. The user sees Kdenlive close and reopen; 1–2
   seconds of downtime. No key injection, no fragile dialog automation.

4. **QFileSystemWatcher + KMainWindow.setCaption** — *can't* force a
   reload from inside Kdenlive without one of the above. The watcher
   can detect the change, but Kdenlive offers no method to act on it.

**Recommendation:** option 3 (quit + relaunch with file path) for v1 of
Phase 5. It's simple, race-free, works without `xdotool`, and matches
what a human would do if a friend said "your project has new changes,
reopen it." Revisit option 1 in Phase 8 if a real "reopen current file
from disk" method gets added to Kdenlive's MainWindow D-Bus interface.

## Side finding (very useful for Phase 7/8)

`/kdenlive/MainWindow_1` exposes a real, **upstream Kdenlive** D-Bus
interface at `org.kde.kdenlive.MainWindow` with methods that the
guide's findings doc claimed didn't exist on upstream:

```
addProjectClip(s url, s folder)
addTimelineClip(s url)
addEffect(s effectId)
scriptRender(s url)
slotReloadEffects(as paths)
updateProjectPath(s path)
slotUpdateDocumentState(b modified)
fetchFolderSize(s path) -> t
cleanRestart(b clean, b forceQuit)
setRenderingProgress(s url, i progress, i frame)
setRenderingFinished(s url, i status, s error)
exitApp()
```

These are not 108 like `D-Ogi/kdenlive`, but they cover:
"add a clip to the bin," "add a clip to the timeline," "add an effect
to the active clip," and "render a script." That's enough to do a
non-trivial subset of edits live, **without** the fork.

This is a **material deviation from the guide's findings doc**, which
should be amended when the user next touches the guide. Phase 0
intentionally didn't update the guide text in this run — that's a
content decision the human should make after seeing the evidence.
