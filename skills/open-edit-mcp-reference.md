---
name: open-edit-mcp-reference
description: >-
  IR ops and run_script recipes for Open Edit MCP. Read when applying timeline
  ops (add_clip, trim, silence application) or when the playbook is not enough.
---

# Open Edit MCP reference

Companion to `skills/open-edit-mcp.md`.

## Example tool arguments

**List assets**
```json
{"query": "list_assets", "params": {}}
```

**Ingest**
```json
{
  "operation": "ingest_local",
  "params": {
    "paths": ["/absolute/path/to/clip.mp4"],
    "transcribe": true
  }
}
```

**Silence cuts**
```json
{
  "generate": "silence_cuts",
  "generate_params": {
    "asset_hash": "<hash-from-list_assets>",
    "threshold_ms": 400
  }
}
```

**Proxy render**
```json
{"mode": "proxy"}
```

## When to use `run_script`

Pillar `edit_project` does **not** include `add_clip` / `trim_clip` /
`remove_clip`. Use `run_script` for timeline construction:

- Place / order / trim clips
- Bulk rebuild from silence-gap proposals
- Raw MLT / free-form escape hatches

Sandbox header is auto-injected — do not add it manually.

### Minimal add_clip sketch

```python
# Prefer the IR API available in the sandbox.
# Typical fields: asset_hash, track_id, position_sec, in_point_sec, out_point_sec
ir.add_clip(
    asset_hash=ASSET_HASH,
    track_id="video1",
    position_sec=0.0,
    in_point_sec=0.0,
    out_point_sec=DURATION_SEC,
)
```

If unsure of helper names, a tiny probe that prints available symbols is OK —
do **not** grep the whole Open Edit repo.

## IR op kinds (high level)

**Clips:** `add_clip`, `remove_clip`, `move_clip`, `trim_clip`, `slip_clip`,
`ripple_delete_clip`, `change_clip_speed`, `split_clip`, `replace_clip_source`,
`set_clip_speed_ramp`

**Transitions:** `add_transition`, `remove_transition`, `set_transition_property`

**Effects:** `add_effect`, `remove_effect`, `set_effect_param`, `set_keyframe`,
`remove_keyframe`

**Audio:** `set_audio_gain`, `normalize_audio`

**Overlays:** `add_html_overlay`, `remove_html_overlay`,
`add_remotion_composition`, `remove_remotion_composition`

**Escape:** `raw_mlt_xml`, `free_form_code`, `undo`

Edit graph is append-only; “undo” = new op that reverts/supersedes.

## Dual process (MCP + review UI)

| Process | Role |
|---|---|
| MCP (`open-edit-mcp`) | Agent tools |
| `open_edit serve --review-only` | Preview, scrub, notes, revert |

Notes from the UI → `query_project` / `get_pending_notes`.

## Env knobs (config, not code)

| Env | Purpose |
|---|---|
| `OPEN_EDIT_INGEST_ALLOWLIST` | Colon-separated absolute roots for ingest |
| `OPEN_EDIT_WHISPER_LANGUAGE` | e.g. `ar` |
| `OPEN_EDIT_WHISPER_MODEL` | e.g. `small` |
| `OPEN_EDIT_NODE_BIN` | Node for Remotion |
| `OPEN_EDIT_AUTO_PROXY` | Auto proxy after graph changes (serve) |
| `OPEN_EDIT_SKILLS_DIR` | Override directory for harness skill markdown |

## Authoritative code (debug Open Edit only)

- `open_edit/kernel/tool_registry.py` — pillar schemas
- `open_edit/kernel/pillar_tools.py` — dispatch
- `open_edit/mcp/adapters.py` — MCP → kernel
- `open_edit/kernel/tool_schemas.py` — `TOOL_USAGE_GUIDE` / IR summary
