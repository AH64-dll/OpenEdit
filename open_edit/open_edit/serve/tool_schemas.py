"""Hand-written function-calling schemas for the Open Edit agent tools.

These schemas are NOT auto-generated. Each one is a hand-tuned JSON Schema
matching the actual ``args: dict`` shape that the corresponding function in
``open_edit/agent/tools/`` expects. Keep them in sync with the tool
docstrings when the underlying tools change.

The 12 tools below mirror ``open_edit/agent/tools/`` 1:1. A 13th virtual
tool ``trigger_render`` is included: it is **server-side only** (not in
``open_edit.agent.tools``) and is handled specially by the agent loop to
shell out to ``open_edit render``.

v1.4 P1-1 added ``search_assets`` and ``import_asset`` (12 real + 1 virtual
= 13 in total). The pi TS extension auto-discovers new entries from this
list, so no extension changes are needed when tools are added.

Each schema follows the Anthropic tools shape::

    {
        "name": str,
        "description": str,
        "input_schema": { JSON Schema }
    }
"""
from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict[str, Any]] = [
    # 1 -----------------------------------------------------------------
    {
        "name": "add_marker",
        "description": (
            "Append a ReviewNote (a marker) at a specific timestamp on the "
            "timeline. Use this to flag something for the user to review — "
            "e.g. a silence cut suggestion, a beat where the music should "
            "drop, or a moment that needs B-roll. The note is created with "
            "source='agent' so the UI can distinguish agent notes from "
            "user notes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "t_start": {
                    "type": "number",
                    "description": "Position on the timeline in seconds (float).",
                },
                "t_end": {
                    "type": "number",
                    "description": "Optional end timestamp in seconds; defaults to t_start.",
                },
                "text": {
                    "type": "string",
                    "description": "The review note text. Be specific and actionable.",
                },
            },
            "required": ["t_start", "text"],
        },
    },
    # 2 -----------------------------------------------------------------
    {
        "name": "analyze_narrative",
        "description": (
            "Analyse the narrative structure of an asset (or the whole "
            "timeline if no asset_hash is given). Returns a list of "
            "segments with start/end timestamps, a label, and a one-line "
            "summary. Use this BEFORE proposing cuts, music, SFX, or "
            "motion graphics — every other creative tool benefits from "
            "knowing the narrative arc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "asset_hash": {
                    "type": "string",
                    "description": "Hash of the asset to analyse. Omit to analyse the whole timeline.",
                },
                "granularity": {
                    "type": "string",
                    "enum": ["coarse", "medium", "fine"],
                    "description": "How granular the segments should be. Default 'medium'.",
                },
            },
        },
    },
    # 3 -----------------------------------------------------------------
    {
        "name": "generate_visual_for_segment",
        "description": (
            "Return an AddClipOp for a templated motion graphic matched to "
            "a narrative segment (e.g. 'title card', 'lower-third', "
            "'end-card'). The op is returned to the LLM — it is NOT "
            "automatically inserted into the edit graph. The LLM should "
            "review the op and then call run_python to commit it if it "
            "looks right, or modify it first."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "segment_id": {
                    "type": "string",
                    "description": "The segment id returned by analyze_narrative.",
                },
                "template": {
                    "type": "string",
                    "description": "Template key, e.g. 'title_card', 'lower_third', 'end_card'.",
                },
                "text": {
                    "type": "string",
                    "description": "Text to render in the graphic.",
                },
                "duration_s": {
                    "type": "number",
                    "description": "Optional duration. Defaults to the segment length.",
                },
            },
            "required": ["segment_id", "template"],
        },
    },
    # 4 -----------------------------------------------------------------
    {
        "name": "get_pending_notes",
        "description": (
            "List pending review notes. Returns the first 10 notes in full "
            "plus a count of how many more are pending. Use this at the "
            "start of a turn to see what the user (or a previous agent "
            "turn) has flagged."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "offset": {
                    "type": "integer",
                    "description": "Skip this many notes. Default 0.",
                    "default": 0,
                },
            },
        },
    },
    # 5 -----------------------------------------------------------------
    {
        "name": "get_style_profile",
        "description": (
            "Return the slice of the project's pinned style profile that "
            "applies to a given op type. Use this before generating ops "
            "of that type so the new ops respect the project's established "
            "look & feel (e.g. lower-third font, transition duration)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "op_type": {
                    "type": "string",
                    "description": "Op type key, e.g. 'AddClipOp', 'AddEffectOp'.",
                },
            },
            "required": ["op_type"],
        },
    },
    # 6 -----------------------------------------------------------------
    {
        "name": "place_sfx",
        "description": (
            "Return SFX AddEffectOps for an asset — e.g. whooshes on "
            "transitions, impacts on cuts, ambient beds under quiet "
            "segments. The ops are returned to the LLM for review; they "
            "are NOT committed automatically."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "asset_hash": {
                    "type": "string",
                    "description": "Hash of the asset to place SFX on.",
                },
                "mood": {
                    "type": "string",
                    "description": "Optional mood hint, e.g. 'tense', 'playful', 'epic'.",
                },
            },
            "required": ["asset_hash"],
        },
    },
    # 7 -----------------------------------------------------------------
    {
        "name": "propose_silence_cuts",
        "description": (
            "Return silence-cut suggestions for an asset. Each suggestion "
            "has a start/end timestamp and a confidence score. Use this "
            "when the user asks to tighten pacing or remove dead air. The "
            "suggestions are returned to the LLM — committing them is a "
            "separate step (run_python)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "asset_hash": {
                    "type": "string",
                    "description": "Hash of the asset to analyse.",
                },
                "min_duration_s": {
                    "type": "number",
                    "description": "Minimum silence length to flag, in seconds. Default 0.5.",
                    "default": 0.5,
                },
                "threshold_db": {
                    "type": "number",
                    "description": "Volume threshold in dBFS below which audio counts as silence. Default -40.",
                    "default": -40,
                },
            },
            "required": ["asset_hash"],
        },
    },
    # 8 -----------------------------------------------------------------
    {
        "name": "run_python",
        "description": (
            "Run free-form Python in the bwrap+seccomp sandbox to commit "
            "ops to the edit graph, query the DB, or compose multi-step "
            "edits. Use this when no single dedicated tool fits — e.g. "
            "'add a fade-out to the first clip' needs to fetch the first "
            "clip op, build an AddEffectOp with type='fade_out', and "
            "append it. The sandbox has access to ``open_edit`` modules "
            "and to the project path. Output (print/return value) is "
            "captured and returned as the tool result."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python source to execute. Must be self-contained.",
                },
                "timeout_s": {
                    "type": "integer",
                    "description": "Timeout in seconds. Default 30.",
                    "default": 30,
                },
            },
            "required": ["code"],
        },
    },
    # 9 -----------------------------------------------------------------
    {
        "name": "select_music",
        "description": (
            "Return music-bed AddEffectOps for an asset. Picks a track "
            "from the music library based on the asset's mood/pace (as "
            "inferred from the narrative analysis) and the project's "
            "style profile. Ops are returned for review; not committed "
            "automatically."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "asset_hash": {
                    "type": "string",
                    "description": "Hash of the asset to score.",
                },
                "mood": {
                    "type": "string",
                    "description": "Optional mood hint to override the inferred one.",
                },
                "bpm_target": {
                    "type": "integer",
                    "description": "Optional target BPM. Default: pick from style profile.",
                },
            },
            "required": ["asset_hash"],
        },
    },
    # 10 ----------------------------------------------------------------
    {
        "name": "set_pinned_value",
        "description": (
            "Pin a key=value pair in the project's global style profile. "
            "Use this when the user expresses a stylistic preference that "
            "should apply to future ops too — e.g. 'always use 12px lower "
            "thirds' or 'transitions should be 0.3s cross-dissolves'. "
            "Pinned values override inferred defaults."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "Dotted key path, e.g. 'lower_third.font_size' or 'transition.default_duration_s'.",
                },
                "value": {
                    "description": "Any JSON value (string, number, bool, object, array).",
                },
            },
            "required": ["key", "value"],
        },
    },
    # 11 (virtual / server-side) ---------------------------------------
    {
        "name": "trigger_render",
        "description": (
            "Trigger a render of the current edit graph. Use this when "
            "the user says 'render it', 'give me a preview', or 'export "
            "the final cut'. Modes: 'proxy' (fast, low-res preview), "
            "'final' (full quality), or 'overlay' (v1.6 HTML overlay "
            "composited pipeline; requires at least one HtmlOverlay in "
            "the timeline). Returns the output path when done. This is a "
            "server-side tool — it is handled by the agent loop, not by "
            "open_edit.agent.tools."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["proxy", "final", "overlay"],
                    "description": "Render mode. 'overlay' triggers the v1.6 HTML overlay composited pipeline (requires at least one AddHtmlOverlayOp in the timeline). Default 'proxy'.",
                    "default": "proxy",
                },
            },
        },
    },
    # 12 (v1.4 P1-1) ---------------------------------------------------
    {
        "name": "search_assets",
        "description": (
            "Search the internet for stock media (video, photo, or audio) "
            "to use in the project. Dispatches to Pexels (video/photo) or "
            "Freesound (audio). Returns a normalised list of results with "
            "id, source, kind, title, thumbnail_url, preview_url, "
            "duration_seconds, license, and attribution_required — the UI "
            "renders the thumbnails with the license badge and an 'Add to "
            "project' button that fires import_asset. Cached in-memory for "
            "5 minutes so an iterative search loop doesn't burn the Pexels "
            "20k/month cap. If the relevant API key is missing, returns a "
            "structured error (not a crash) — surface it to the user."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Free-text search query, e.g. 'rain b-roll', "
                        "'whoosh sound effect', 'sunset over mountains'."
                    ),
                },
                "kind": {
                    "type": "string",
                    "enum": ["video", "photo", "audio"],
                    "description": (
                        "Which kind of media to search for. 'video' and "
                        "'photo' go to Pexels; 'audio' goes to Freesound."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": (
                        "Max number of results to return. Default 8. "
                        "Capped at 40 to keep responses tractable."
                    ),
                    "default": 8,
                },
            },
            "required": ["query", "kind"],
        },
    },
    # 13 (v1.4 P1-1) ---------------------------------------------------
    {
        "name": "import_asset",
        "description": (
            "Import a third-party media asset (returned by a prior "
            "search_assets call, or a direct HTTPS URL) into the project's "
            "content-addressed asset store. Downloads the file, ingests it "
            "via AssetStore, and tags the resulting Asset with license + "
            "attribution metadata so the credit line is visible later. "
            "For a result_id, the license/attribution are pulled from the "
            "search cache (so the LLM doesn't have to re-pass them); for "
            "a bare source_url, supply license + attribution explicitly "
            "or accept the 'Unknown' default. Requires HTTPS."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "result_id": {
                    "type": "string",
                    "description": (
                        "ID of a result from a prior search_assets call. "
                        "Preferred over source_url because the cached "
                        "metadata (license, attribution) is reused."
                    ),
                },
                "source_url": {
                    "type": "string",
                    "description": (
                        "Direct HTTPS URL to the media file. Use this when "
                        "you don't have a result_id (e.g. the user pasted "
                        "a link). Must be HTTPS."
                    ),
                },
                "license": {
                    "type": "string",
                    "description": (
                        "Human-readable license string, e.g. 'Pexels "
                        "License', 'CC BY 4.0', 'CC0 1.0'. Defaults to "
                        "'Unknown' when neither this nor a cached result "
                        "provides one."
                    ),
                },
                "attribution": {
                    "type": "string",
                    "description": (
                        "Credit line to display, e.g. \"'rain' by "
                        "alice (CC BY 4.0)\" or 'Source: Pexels'. "
                        "Defaults to empty when unknown."
                    ),
                },
            },
        },
    },
]


# Convenience lookup
TOOL_BY_NAME: dict[str, dict[str, Any]] = {t["name"]: t for t in TOOL_SCHEMAS}


def get_tool_schema(name: str) -> dict[str, Any] | None:
    """Return the schema for a tool by name, or None if unknown."""
    return TOOL_BY_NAME.get(name)


# ---------------------------------------------------------------------------
# "When to use each tool" guide — embedded in the system prompt
# ---------------------------------------------------------------------------

TOOL_USAGE_GUIDE = """\
## When to use each tool

- **Always start with context.** If the user's request is about the project
  as a whole, call `list_assets` and `get_pending_notes` first. If it's
  about a specific asset but you don't know its hash, call `list_assets`.
- **For creative edits on a single asset**, call `analyze_narrative` first
  to understand the asset's structure, then propose ops with the dedicated
  tools (`place_sfx`, `select_music`, `generate_visual_for_segment`,
  `propose_silence_cuts`).
- **Dedicated tools return op drafts, not committed ops.** To actually
  insert an op into the edit graph, call `run_python` with code that
  builds and appends the op using the open_edit IR helpers.
- **For one-off edits that don't fit a dedicated tool** (e.g. "add a
  fade-out to the first clip"), call `run_python` directly. Compose the
  op, append it to the graph, and print a short confirmation.
- **For style decisions the user states explicitly**, call
  `set_pinned_value` so the preference sticks for future turns.
- **Before generating ops of a given type**, call `get_style_profile` to
  respect the project's pinned style.
- **To render**, call `trigger_render` with `mode: "proxy"` (default) or
  `mode: "final"`. Do NOT try to call `open_edit render` from inside
  `run_python` — the sandbox doesn't allow subprocess calls.
- **After every render, you MUST look at the sampled frames** attached to
  the tool result and respond with `VERIFICATION: PASS|FAIL|UNCERTAIN` on
  its own line. "PASS" only if the frames look correct; iterate otherwise.
- **To leave a flag for the user**, call `add_marker` at the relevant
  timestamp with a short, specific note.
- **To find stock media** (b-roll, SFX, ambience), call `search_assets`
  with `kind` in ('video', 'photo', 'audio'). Results surface in the UI
  with thumbnails + license badges; the user clicks "Add to project"
  (or you can call `import_asset` directly with a result_id). Audio
  results are preview-quality (lossy MP3); full-quality audio is a
  fast-follow requiring Freesound OAuth2.
- **To import a third-party asset** the user picked from a search,
  call `import_asset` with the result_id (license/attribution come from
  the search cache) or a direct `source_url` (supply them yourself).
"""


# ---------------------------------------------------------------------------
# IR op model summary — also embedded in the system prompt
# ---------------------------------------------------------------------------

IR_MODEL_SUMMARY = """\
## Open Edit IR (intermediate representation) summary

The edit graph is an **append-only log of ops** stored in
``edit_graph.db`` (table ``edits``). Every op has these base fields:
``edit_id, parent_id, kind, author, timestamp, status, sequence_num, payload``.
Status is one of ``applied | reverted | superseded``. To "modify" an op,
you add a new op that supersedes it (via ``parent_id`` linking).

There are **24 concrete op kinds** in ``open_edit.ir.types``. The
``kind`` field is the operation class name in snake_case. The full list:

**Clip ops** (manage clips on tracks):
- ``add_clip`` — add a clip from an asset. Payload: ``{asset_hash, track_id, position_sec, in_point_sec, out_point_sec}``.
- ``remove_clip`` — remove a clip by op_id. Payload: ``{clip_id}``.
- ``move_clip`` — move a clip to a new position. Payload: ``{clip_id, new_position_sec, new_track_id?}``.
- ``trim_clip`` — change in/out points. Payload: ``{clip_id, new_in_sec, new_out_sec}``.
- ``slip_clip`` — slide source window without changing clip length. Payload: ``{clip_id, delta_sec}``.
- ``ripple_delete_clip`` — remove a clip and shift subsequent clips. Payload: ``{clip_id}``.
- ``change_clip_speed`` — retime. Payload: ``{clip_id, new_speed}``.
- ``split_clip`` — split a clip at a position. Payload: ``{clip_id, split_at_sec}``.
- ``replace_clip_source`` — point a clip at a different asset. Payload: ``{clip_id, new_asset_hash}``.
- ``set_clip_speed_ramp`` — variable speed. Payload: ``{clip_id, ramp_points[]}``.

**Transition ops**:
- ``add_transition`` — add a transition between two clips. Payload: ``{from_clip_id, to_clip_id, transition_type, duration_sec}``.
- ``remove_transition`` — remove a transition. Payload: ``{transition_id}``.
- ``set_transition_property`` — change a transition's params. Payload: ``{transition_id, property, value}``.

**Effect ops**:
- ``add_effect`` — add an effect to a clip or the timeline. Payload: ``{target_clip_id?, effect_type, params}``.
- ``remove_effect`` — remove an effect. Payload: ``{effect_id}``.
- ``set_effect_param`` — change a single effect param. Payload: ``{effect_id, param, value}``.
- ``set_keyframe`` — set a keyframe. Payload: ``{effect_id, time_sec, value}``.
- ``remove_keyframe`` — remove a keyframe. Payload: ``{keyframe_id}``.

**Audio ops**:
- ``set_audio_gain`` — change clip volume. Payload: ``{clip_id, gain_db}``.
- ``normalize_audio`` — normalize audio. Payload: ``{clip_id, target_dbfs}``.

**Grouping ops**:
- ``group_edits`` — group ops into an atomic block. Payload: ``{edit_ids[]}``.
- ``ungroup_edits`` — dissolve a group. Payload: ``{group_id}``.

**Escape hatches**:
- ``raw_mlt_xml`` — paste raw MLT XML. Payload: ``{xml, scope}``.
- ``free_form_code`` — embed Python code (the result of ``run_python``). Payload: ``{code, project_id, parent_op_id}``.

**Other ops** (less common, mainly for migrations and power users):
- ``undo`` — revert a previous op. Payload: ``{op_id}``.

**Common fields** every op carries (inherited from the ``Operation`` base):
``edit_id`` (UUID), ``parent_id`` (UUID of the op this one descends from;
``None`` for root ops), ``author`` (e.g. ``"agent"``, ``"user"``),
``timestamp`` (ISO 8601 string), ``status``, ``sequence_num`` (auto-assigned
by ``EditGraphStore``), ``payload`` (JSON blob of op-specific data).

**To build an op programmatically**, use ``open_edit.ir.api.IR``. Each
op type has a method on the ``IR`` class (e.g. ``ir.add_clip(...)``,
``ir.add_effect(...)``, ``ir.slip_clip(...)``). The agent's ``run_python``
tool gives you access to ``IR`` and the op classes inside the bwrap
sandbox.

**Review notes** are NOT ops. They live in ``notes.db`` (table ``notes``)
with fields ``note_id, project_id, anchor_type, anchor, text, source,
status, created_at, processed_at, commit_token, resulting_op_ids``.
``anchor`` is JSON-encoded (e.g. ``'{"t_start": 3.2, "t_end": 3.5}'`` for a
timestamp anchor). Use the ``add_marker`` tool to create agent-sourced
notes.

**Style profile** is a separate key/value store pinned at the project
level. Pinned values override inferred defaults when generating new ops.
Use ``set_pinned_value`` to pin, ``get_style_profile`` to read the slice
for a given op kind.
"""
