# Editable object tracking

This implements the subsequently requested tracking workflow alongside the
existing diffusion plan. The original plan and its milestone IDs remain unchanged.

## Workflow

Select a rectangle on the video preview, choose its source clip, a timeline range
and forward/backward/both directions, then start local analysis. Foreground mode
uses GrabCut to identify a component within the rectangle; exact-region mode
keeps the selected box. CSRT tracks appearance through locally decoded frames.
No provider request is made for individual frames. Analysis uses at most 960x540
pixels, defaults to 15 samples/second, supports 1–30 samples/second and ranges up
to 300 seconds. Decode blocks are limited to two seconds with a 30-second timeout.

Analysis is a background job with progress and cancellation. Completed results
persist under `.open_edit/tracking/jobs`. A completed result is applied explicitly
at the current graph revision. A retracking result cannot overwrite an object
changed while analysis was running. Interrupted analysis is reported as failed
when its owner process no longer exists; it can be started again.

## Editable source

An `object_track` studio object and matching `set_object_track` IR operation store
the stable target ID, clip ID, original asset hash, label, algorithm provenance,
enabled/locked state, ordered motion samples and independent effect IDs. Boxes
use normalized original-source coordinates; sample times use original-source
seconds. Moving/slipping/trimming a clip retains these coordinates. Splitting
and duplicating through the shared studio commit copies tracks and effects with
independent identities, in the same history action; the original object ID stays
with the left split. Low-level writers cannot silently split a tracked clip or
write tracking IR without matching studio source changes.

Manual corrections replace or insert one source-time sample. Samples can be
deleted, and a corrected region can seed another local pass. Following highlight,
label, cover, blur and pixelate effects expose text, color, strength, padding,
offset and scale. Effects and whole tracks can be disabled/deleted independently.
Locks, guarded revisions, Undo/Redo and selective AI request inverses share the
existing editor transaction path.

Tracking failure produces invalid samples rather than extrapolated motion.
Following effects stop across invalid samples. The appearance score is a
diagnostic, not a probability. A correction/retracking pass is required after
loss; automatic re-identification after occlusion is not promised.

## Preview, export and AI

The render planner builds cached, lossless alpha graphics or grayscale masks
from the same source used by the inspector. Source boxes are fitted to the render
canvas with the video's aspect ratio. Blur/pixelation modifies the actual
composited image through a moving mask, so prior color/effect changes are retained.
Materialization covers only the intersection of the tracked source range and
the visible clip. Automatic preview chunks, full-quality range previews and
immutable local exports use this path.

Chunk slices retain only neighboring motion samples needed for interpolation.
Tracking changes affect the video plane; audio remains reusable. Lock,
confidence and provenance metadata do not change visual chunk keys. The preview
audio pipe also uses the actual WAV muxer (`f=wav`, PCM), fixing unavailable
playback when video rendered but the piped audio pass failed.

The existing six public tools expose `start_tracking`, `cancel_tracking`,
`apply_tracking_job`, `edit_object_track` and `get_tracking_job`. Default editing
context returns the target's source range, current box, three representative
samples and at most ten lost ranges. Full motion source is opt-in through
`get_studio(kind="object_track", object_id=..., include_source=true)`; small AI
edits retain unmentioned samples without transmitting them. A 9,001-sample test
asserts context remains below 7 KB.

## Scope and acceptance

This is seeded foreground/box tracking. Semantic naming, exact object outlines
and background reconstruction/inpainting remain separate capabilities. Speed
and spatial transformations require baking to a source and retracking; the
editor rejects unsupported combinations instead of exporting misplaced effects.
Changed/missing original sources are reported and do not receive stale effects.

`tests/test_object_tracking.py` exercises real moving footage, foreground
identification, occlusion/loss, cancellation, concurrent edits, manual corrections,
locks/history, split/duplicate independence, compact context, source-time masks
after trimming/moving, and actual FFmpeg composition. The platform workflow runs
it on Linux, macOS and Windows. `tests/browser/object-tracking.cjs` exercises real
pointer selection, local analysis, following-effect controls, locks, automatic
preview, full-quality sliced preview, local export pixels at two target positions
and reopening. Browser evidence is written under `tests/browser/artifacts`.
