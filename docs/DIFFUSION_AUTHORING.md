# Diffusion JSX authoring through MCP

The optional authoring adapter exports OpenEdit media clips as literal JSX and
translates edits back into the existing operation graph. SQLite remains the
source of truth. It uses the pinned Diffusion Studio compiler and AST source
writer. The separate optional [graphics worker](DIFFUSION_GRAPHICS.md) uses the pinned
Diffusion runtime; the Electron application is not required.

## Setup

Exporting a view works with the default Python installation. Applying source
edits additionally needs Node.js and npm. Node 24 is the tested version. Install
the worker's locked dependencies once, using the Python environment that runs
your MCP server:

```bash
python -m open_edit.integrations.diffusion.setup
```

This explicitly runs `npm ci --ignore-scripts --no-audit --no-fund` in the
packaged worker directory. MCP startup never downloads these dependencies.
The Python wheel includes worker source and its lockfile, without node_modules.
For a read-only Python installation, copy the packaged `worker` directory to a
writable location and set `OPEN_EDIT_DIFFUSION_WORKER_DIR` to that copy for both
setup and the MCP server. No Chromium installation is needed for authoring.

## Read a view

Call the existing `query_project` tool:

```json
{"query":"get_authoring_view","params":{}}
```

The compact result includes `graph_revision`, clip and track counts,
`worker_ready`, track source IDs, supported edits and preserved feature counts.
Request source only when you need it:

```json
{"query":"get_authoring_view","params":{"include_source":true}}
```

The `source` field contains a document like:

```tsx
export default function OpenEditProject() {
  return (
    <stage id="openedit">
      <scene id="main" width={1920} height={1080} active>
        <group id="t-main">
          <video id="c-hero" src={"asset://video"} start={0} sourceIn={0} sourceOut={5} playbackRate={1} volume={0} />
        </group>
      </scene>
    </stage>
  );
}
```

Actual `src` values use existing CAS asset hashes. `c-` and `t-` prefix clip and
track identities; characters such as colons and slashes are URL-escaped. Keep
the exported IDs to preserve identity. For example, clip `hero:1` has element
ID `c-hero%3A1` and source ID `index.tsx:c-hero%3A1`.

## Apply edits atomically

Call `edit_project` with the revision from your view. The example revision is
illustrative; always supply the actual exported value:

```json
{
  "operation": "apply_authoring_edit",
  "params": {
    "expected_revision": 3,
    "edits": [
      {
        "kind": "set",
        "source": "index.tsx:c-hero",
        "props": {"start": 3, "sourceIn": 2, "sourceOut": 7, "volume": -6}
      }
    ]
  }
}
```

The upstream source writer applies each edit to a temporary source document.
The host parses and compiles the result, validates every clip and commits the
resulting IR operations in one SQLite transaction. `volume` is an **absolute
decibel value**. The adapter accounts for existing cumulative gain effects.

Native source edits support:

| Kind | Fields | Behavior |
|---|---|---|
| `set` | `source`, `props` | Set `start`, `sourceIn`, `sourceOut`, `playbackRate`, `volume` or `src` |
| `remove` | `source` | Remove the identified clip |
| `move` | `source`, `parent`, optional `before` | Reparent a clip to an existing compatible track; `before` is a source-writer anchor |

To add clips or append a track, edit the complete exported JSX document and
pass it as `params.source` instead of `params.edits`. New tracks require at
least one clip. Existing tracks must retain their IDs and order. Visual order
within a track is determined by each clip's `start`, not its line order.

A successful result reports the new `graph_revision`, `ops_appended`, changed
clip IDs (first 50), total changed count and a compilation hash. It does not
return another full document. Query again when you need a fresh source view.
An unchanged document appends no operations and does not advance the revision.
If another editor changes the graph during compilation, the entire batch fails
with `error_code: "stale_revision"` and the current revision. Read the latest
view and reapply the intended changes. A stale unchanged document also fails.

## Current boundaries

- Supported media: video, audio (including audio from a video asset) and still
  images, with explicit positive source ranges, nonnegative timing, no overlap
  within a track and known project assets. Put simultaneous media on separate
  tracks. Audio/video ranges must fit asset duration.
- Supported changes: add, remove, move, trim, replace source and constant
  volume from -120 to +24 dB and playback rates from 0.125 to 8. Images have no
  audio volume. Non-unity rates first materialize lossless, pitch-preserving CAS
  media and pass duration/audio/decode checks. At most 20 changed retimed clips
  per transaction, 60 seconds and 1,800 frames per output. Existing legacy speed
  effects, normalized volume and keyframed gain remain outside this view.
- Source is one default function returning one stage, one scene, track groups
  and media leaves with literal props. Imports, calls, arbitrary expressions,
  spreads, loops, text, shapes and component expansion are rejected. Project
  JavaScript is never evaluated, and project Babel configuration is not loaded.
- Existing visual effects, track effects, HTML overlays and legacy Remotion
  entries remain in the graph. They are not editable or visually represented
  in this media document. Removing a clip removes that clip's own effects.
- Scene dimensions are fixed authoring metadata. Existing render profiles and
  backends still determine output dimensions and render behavior.
- Limits: 2,000 media clips, 512 KiB of source, 1 MiB worker requests/responses,
  1,000 native source edits and a 20-second compiler timeout. Large projects can
  continue using the structured timeline tools.

Accepted source formatting and comments are stored in SQLite with the exact
graph revision, in the same transaction as the operations. A formatting-only
save changes neither the graph nor its revision. The last eight accepted
revision views are retained. After another editor mutates the graph, reads
regenerate source from that new graph snapshot; an older source is never served
as current. Compilation errors, skipped edits, timeouts and transaction failures
preserve the last accepted source and graph.

## Review Studio editor

Open **JSX editor** below the preview to edit source or a selected clip's start,
source range, playback rate and volume. Both paths call the same revision-checked adapter as
MCP. The clip controls show the first 50 clips; the code view covers the full
supported document. Code drafts are kept in the browser tab's session storage.
Apply or reload a code draft before using clip controls.

If another editor changes the graph, the editor keeps your draft and disables
Apply. Copy the intended changes before choosing **Reload source**, then reapply
them to the latest document. Reload source explicitly discards the current
draft. Compiler errors leave the text available for correction. Native UI
changes are recorded with `author=user`.

`GET /api/projects/{id}/authoring?include_source=true` and
`POST /api/projects/{id}/authoring` expose the same adapter to the UI. Writes
require an integer `expected_revision` and exactly one of `source` or `edits`;
stale writes return HTTP 409 with the current graph revision.

For text, shapes, masks, basic animations and sequence transitions, use the
separate [Graphics studio and MCP workflow](DIFFUSION_GRAPHICS.md). Constant JSX
rates retain their original asset/range in versioned CAS provenance; another
editor trimming that baked clip is reflected back into original source time.
Older `change_clip_speed` and speed-ramp operations keep their original replay
semantics. `retime_asset` can explicitly bake piecewise-constant source segments
without changing the graph. See [validation](DIFFUSION_EXECUTION_VALIDATION.md).
