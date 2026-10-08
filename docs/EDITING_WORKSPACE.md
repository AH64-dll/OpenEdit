# Editing workspace

Run `open_edit serve` and open the printed local URL. Review mode is the default;
projects, media, operations and render jobs remain in the existing project store.
The Diffusion implementation plan is unchanged.

## Setup and optional capabilities

Use **Setup** or `open_edit doctor --json` to check readiness. Checks verify
FFmpeg's libx264 support, ffprobe, melt, Node 24+, npm, optional worker packages,
and Chromium. They explain installation steps without downloading anything.

- Full FFmpeg and MLT/melt: timeline previews and video export.
- `open_edit setup media`: clip properties and literal project JSX edits.
- `open_edit setup graphics`: editable Diffusion graphics and Chromium.
- `open_edit setup html`: advanced HyperFrames HTML/CSS/JS overlays.
- `open_edit setup legacy-remotion`: pinned Remotion 4.0.278 / React 18.3.1
  compatibility, independently installed in `integrations/remotion`.

Install optional packages using the Python environment running OpenEdit. For a
read-only Python installation, copy `integrations/remotion` to a writable
location, run `npm ci --ignore-scripts` there, and set
`OPEN_EDIT_REMOTION_PACKAGE` to that directory. Existing project-local Remotion
installs and explicit `OPEN_EDIT_REMOTION_CLI`/`OPEN_EDIT_REMOTION_BIN` wrappers
retain precedence. Missing compatibility dependencies produce setup instructions;
the renderer never fetches an unpinned CLI through npx.

The Python package includes the workspace and MCP. Built-in chat is an optional
extension: install `open-edit[agent]`, then launch with `--with-agent`. Review
startup does not import agent/provider implementations or load browser chat/WS
modules. Existing optional API URLs remain compatible.

## Review, Graphics and Code

**Review** shows the timeline preview and one transport with seek, volume and
fullscreen. Select a timeline clip to edit it in the right inspector. **Graphics**
shows the editable canvas, layer inspector and checked graphics preview. Expand
**Edit graphics source** for its JSX. **Code** shows project source. All views
share the timeline; changing views does not discard drafts. On small screens,
selecting a clip opens the inspector drawer, also available from the panel button.

Source and graphics changes retain revision guards. A conflict keeps your draft
and disables applying it; copy intended changes, reload, then reapply to the latest
project. Ordinary clip controls pause while project source has an unsaved draft.
Graphics enter the timeline only after explicit preview/QC and **Add to timeline**.

The placeholder Style panel and duplicate native main playback controls are
removed. Clip names use media filenames. Outputs use readable names and offer
Download; internal IDs and worker diagnostics live under Details. Export defaults
to **Auto**, with manual CPU/GPU preferences under Advanced export settings.

## Automatic previews

Opening a nonempty timeline or receiving a new graph revision schedules a preview
after a short debounce. The existing dirty-range worker reuses checked unchanged
chunks and renders changed ranges. Playback seeks across the cached chunks.

**Current** means every playback range matches the displayed revision and is
checked. **Updating…** keeps the previous checked preview playable. **Outdated**
means the shown media does not cover the latest revision or an update failed;
Refresh preview retries. **Setup needed** links the workflow to missing tools.
An empty timeline clears the player. Switching projects cancels this UI's pending
work and prevents late responses from replacing the new project's media.

Only automatic jobs owned by this browser session are cancelled when obsolete;
external agent and manual export jobs keep their normal lifecycle. Set
`OPEN_EDIT_AUTO_PREVIEW=0` for manual refresh. `OPEN_EDIT_PREVIEW_CHUNKS=0` remains
the server-side feature gate. There is no automatic graphics-draft commit.

## One action history

Undo/Redo in the toolbar, `open_edit undo` / `open_edit redo`, and MCP share the
same durable history. A validated operation batch is one action, reverted or
restored atomically. Source-only formatting saves do not create empty actions;
authored comments are restored along with the corresponding timeline state.
Shortcuts are Ctrl/Cmd+Z, Ctrl/Cmd+Shift+Z or Ctrl+Y outside text fields, where
native text undo remains available.

MCP clients read `query_project` with `query=get_history`, then call `edit_project`
with `operation=undo` or `redo` and `params.expected_revision`. HTTP uses
`GET /api/projects/{id}/history` and `POST .../history/{undo|redo}`. Stale writers
are rejected. A new action abandons the redo branch. Old projects migrate each
applied operation into a separate action because historical batch boundaries
cannot be recovered. Already reverted/superseded operations do not become a fake
redo stack. Legacy direct status, reorder and delete APIs create a history barrier
so dependent operations cannot be replayed into an inconsistent timeline.
