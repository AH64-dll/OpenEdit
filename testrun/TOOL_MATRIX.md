# OpenEdit MCP Tool Matrix — scratch_proj (tool-verifier)

Project: `/home/amr/apps/mlt-pipeline/testrun/scratch_proj` · project_id `a0d2ceed-58d6-4e66-9bb8-0140fab051e8` · every call logged to `.open_edit/mcp_calls.jsonl`

**Counts:** PASS=30 · FAIL=2 · ENV-LIMITED=3 · SKIP=1 (SKIP not counted)

| # | tool | call | status | result snippet (first 200 chars) | notes |
|---|------|------|--------|-----------------------------------|-------|
| 1 | query_project | list_assets (detail=true) | PASS | `{"assets": [{"codec": "h264", "duration_s": 7.928005, "filename": "take2_color.mp4", "fps": 30.0, "has_audio": true, "hash": "3d7320119753291eb1a5cf3157fa3c4889de0e37d53b84bf8ba77ee527bea4cf", "height` | 4 assets listed with full metadata (codec/fps/res/hash); proxy_status=none |
| 2 | query_project | get_transcript_packed | PASS | `{"asset_hash": "508d5bd374445f8722b6535b596c3c677174b5b2c2863f8d1c1433024cad5b3c", "status": "ok", "transcript_packed": "[00:00.00 - 00:03.12] Um, welcome to open edit.\n*--- Silence (1.06s) ---*\n[00` | 17 words, packed transcript with timestamps + silence markers |
| 3 | query_project | get_silence_gaps (include_fillers=true) | PASS | `{"asset_hash": "508d5bd374445f8722b6535b596c3c677174b5b2c2863f8d1c1433024cad5b3c", "duration_sec": 9.721995, "fillers": [{"t_end": 1.46, "t_start": 0.0, "text": " Um,"}, {"t_end": 4.5, "t_start": 4.18` | 2 silence gaps + 2 fillers (" Um," / " Uh,") |
| 4 | query_project | get_timeline_view (asset 0-6s) | PASS | `{"end_sec": 6.0, "image_path": "/home/amr/apps/mlt-pipeline/testrun/scratch_proj/.open_edit/timeline_views/508d5bd374445f8722b6535b596c3c677174b5b2_0.00-6.00.png", "legend": "shaded bands = silences >` | PNG confirmed on disk: .open_edit/timeline_views/508d…_0.00-6.00.png (126,339 bytes) |
| 5 | query_project | get_timeline_view (path=renders/<mp4>) | SKIP | `—` | no render exists (see RENDER rows); skipped per matrix rule |
| 6 | query_project | get_style_profile (AddEffectOp) | PASS | `{"profile": {"corrections": {"direction": "", "most_overridden_param": "", "note": ""}, "pinned": {"aspect_ratio": "9:16", "subtitle.bar_opacity": "0.72", "subtitle.font_family": "Noto Naskh Arabic, A` | profile with pinned values returned |
| 7 | query_project | get_pending_notes | PASS | `{"notes": [], "remaining_count": 0, "status": "ok"}` | 0 pending notes |
| 8 | query_project | analyze_narrative | PASS | `{"segments": [{"beat_type": "hook", "gap_after_s": 1.0599999999999996, "suggested_visual_concept": "", "t_end": 3.12, "t_start": 0.0, "text": " Um,  welcome  to  open  edit."}, {"beat_type": "turn", "` | 3 segments: hook/turn/button with gaps |
| 9 | query_project | search_assets (rain, video, 2) | ENV-LIMITED | `{"error": "search_assets(video): OPEN_EDIT_PEXELS_API_KEY is not set; set it to search Pexels video, or pass a license=... filter to use Openverse", "results": [], "status": "error"}` | clean error as expected: OPEN_EDIT_PEXELS_API_KEY not set |
| 10 | edit_project | add_clip | PASS | `{"clip_id": "2a4d2585-aa89-4c65-8734-a05abc25d6d0", "kind": "add_clip", "status": "ok"}` | clip_id returned; re-added later for replace/silence ops |
| 11 | edit_project | auto_color_grade | PASS | `{"applied": [{"clip_id": "2a4d2585-aa89-4c65-8734-a05abc25d6d0", "effect_id": "dd808982-58b9-48a7-bbae-437269218dbc", "params": {"contrast": 1.03, "gamma": 1.0, "saturation": 0.96}}], "kind": "auto_co` | effect added: contrast 1.03, saturation 0.96 |
| 12 | edit_project | add_hyperframes_overlay | PASS | `{"engine": "hyperframes", "kind": "add_html_overlay", "overlay_id": "87b85a38-9b63-4541-afd2-fb764adc9174", "status": "ok"}` | overlays/brand_lower_third.html not in scratch proj; created overlays/test.html (trivial div) per instructions and used it |
| 13 | edit_project | set_audio_gain | PASS | `{"clip_id": "2a4d2585-aa89-4c65-8734-a05abc25d6d0", "gain_db": -3.0, "kind": "set_audio_gain", "status": "ok"}` | gain_db -3 |
| 14 | edit_project | add_marker | PASS | `{"note_id": "note_e1ac577efc9e", "status": "ok"}` | note_id returned |
| 15 | edit_project | set_pinned_value | PASS | `{"status": "ok"}` | aspect_ratio=16:9 |
| 16 | edit_project | capture_style_hint | PASS | `{"hint": {"captured_at": "2026-08-06T04:09:51Z", "category": "color", "key": "contrast", "source": "user_confirmed", "text": "prefer punchy contrast"}, "status": "ok"}` | hint captured source=user_confirmed |
| 17 | edit_project | trim_clip | PASS | `{"clip_id": "2a4d2585-aa89-4c65-8734-a05abc25d6d0", "kind": "trim_clip", "status": "ok"}` | 1.2→3.5s |
| 18 | edit_project | change_clip_speed | PASS | `{"clip_id": "2a4d2585-aa89-4c65-8734-a05abc25d6d0", "kind": "change_clip_speed", "rate": 1.25, "status": "ok"}` | rate 1.25 |
| 19 | edit_project | remove_clip | PASS | `{"clip_id": "2a4d2585-aa89-4c65-8734-a05abc25d6d0", "kind": "remove_clip", "status": "ok"}` | removed clip (subsequent ops re-tested on re-added clip) |
| 20 | edit_project | replace_clip_source | PASS | `{"clip_id": "f3c1f176-9ad7-47df-9a94-8154c225ec44", "kind": "replace_clip_source", "status": "ok"}` | swapped to take2 hash |
| 21 | edit_project | apply_silence_gaps | PASS | `{"keep_count": 2, "kind": "apply_silence_gaps", "new_clip_ids": ["50776782-8622-4305-b284-75a734011f8f", "369eb37b-8069-42b7-b308-723d60c6717b"], "removed_clip_id": "f3c1f176-9ad7-47df-9a94-8154c225ec` | clip split into 2 (keep_count=2), snap_to_words+padding 60ms |
| 22 | edit_project | generate=silence_cuts | PASS | `{"gaps": [{"reason": "silence", "suggested_kind": "trim", "t_end": 4.18, "t_start": 3.12}, {"reason": "silence", "suggested_kind": "trim", "t_end": 7.28, "t_start": 6.44}], "status": "ok"}` | 2 trim suggestions; envelope is generate/generate_params (not operation) |
| 23 | edit_project | generate=sfx | PASS | `{"ops": [], "status": "ok", "timing": {"mode": "narrative_transition", "reason": "music_downbeats were not provided; used nearest narrative transition"}}` | ops=[], timing=narrative_transition |
| 24 | edit_project | generate=music | PASS | `{"ops": [], "status": "ok"}` | ops=[] |
| 25 | edit_project | generate=visual (matrix JSON: segment={}) | FAIL | `{"error": "'beat_type'", "status": "error"}` | raw KeyError surfaced: tool requires beat_type/template/params (schema mismatch); dispatch_generate also does not inject project_id (next KeyError was 'project_id'); no clean validation for missing keys |
| 26 | edit_project | generate=visual (full args: beat_type+template+params+project_id) | ENV-LIMITED | `{"error": "render sandbox failed for template 'hook_fade_text' (segment 'hook'): render sandbox failed (exit 1)", "status": "error"}` | structured error: render sandbox failed exit 1 — sandbox env lacks moviepy (ModuleNotFoundError: No module named 'moviepy'); tool reached render stage and failed on env |
| 27 | edit_project | generate=init_remotion | PASS | `{"demo_composition_id": "TitleCard", "entry_point": "src/index.ts", "note": "Remotion is optional; see docs/REMOTION_LICENSE.md", "remotion_root": "/home/amr/apps/mlt-pipeline/testrun/scratch_proj/.op` | scaffolded .open_edit/remotion (src/public/out) |
| 28 | edit_project | generate=write_remotion (matrix JSON) | FAIL | `{"error": "relative_path is required (e.g. src/compositions/MyTitle.tsx)", "expected_keys": ["relative_path", "source"], "status": "error"}` | clean validation error: matrix JSON missing required relative_path/source |
| 29 | edit_project | generate=write_remotion (with required keys) | PASS | `{"bytes": 99, "path": "/home/amr/apps/mlt-pipeline/testrun/scratch_proj/.open_edit/remotion/src/compositions/Cover.tsx", "relative_path": "src/compositions/Cover.tsx", "status": "ok"}` | wrote src/compositions/Cover.tsx (99 bytes) |
| 30 | edit_project | generate=remotion | PASS | `{"clip_id": "69e5600b-61dc-43c6-ad01-783fdd01497f", "composition_uid": "78d3a317-0892-4a57-86b2-0dd445d50d1c", "edit_id": "354d94be-b72f-4622-a716-8488ff5b2d7f", "graph_revision": 13, "kind": "add_rem` | AddRemotionCompositionOp appended (clip_id, composition_uid); note: 'Cover' not registered in scaffolded Root.tsx (only TitleCard) |
| 31 | run_script | print('hello from sandbox') | PASS | `{"error": null, "graph_revision": 13, "ops_appended": 0, "ops_summary": [], "status": "ok"}` | bwrap IS present (/usr/bin/bwrap) → sandbox ran; status ok, ops_appended=0; script stdout not surfaced in tool result (only ops summary); 1st attempt errored on my shell quoting (driver arg), not the product |
| 32 | trigger_render | proxy/cpu/wait=true | ENV-LIMITED | `{"error": "remotion materialize failed for UID '78d3a317-0892-4a57-86b2-0dd445d50d1c' ('Cover'): {\"ok\":false,\"error\":\"remotion produced no output file\"}", "error_code": "render_failed", "ok": fa` | render_failed: remotion materialize failed — Remotion needs Chrome Headless Shell; download from remotion.dev failed, no browser cache on host |
| 33 | get_render_job | real job_id (b54b59c2…) | PASS | `{"created_at": 1785989678.8193839, "edit_graph_hash": "a64070908891e17915ed9a784290da3c3478c44a1967a42bf1fce9c5170c2091", "error": "cancelled", "graph_revision": 13, "job_id": "b54b59c222bf44c5b6e3556` | returns full job record; wait=false job was cancelled when driver/server process exited (CancelledError path) |
| 34 | get_render_job | bogus job_id | PASS | `{"error": "render job not found: bogus-job-123", "ok": false}` | clean error: 'render job not found: bogus-job-123' |
| 35 | cancel_render_job | bogus job_id | PASS | `{"error": "render job not found: bogus-job-123", "ok": false}` | clean error: 'render job not found: bogus-job-123' |
| 36 | trigger_render | proxy/cpu/wait=false (extra) | PASS | `{"job_id": "b54b59c222bf44c5b6e3556d4be0fff5", "message": "Render queued. Poll get_render_job with job_id.", "mode": "proxy", "ok": true, "status": "queued"}` | returns job_id (queued); job then cancelled on process exit — background jobs do not survive driver process (stdio server exits) |

## FAIL detail (verbatim)

1. **generate=visual (matrix JSON `segment:{}`)** — `{"error": "'beat_type'", "status": "error"}` — raw `KeyError: 'beat_type'` surfaced; tool requires `beat_type`/`template`/`params` keys; `dispatch_generate` neither validates them nor injects `project_id` (with beat_type+template it next fails `'project_id'`, then `Unknown template`, then `MotionTemplateParams text Field required`).

2. **generate=write_remotion (matrix JSON)** — `{"error": "relative_path is required (e.g. src/compositions/MyTitle.tsx)", "expected_keys": ["relative_path", "source"], "status": "error"}` — clean validation error; the matrix JSON omitted required keys; happy path verified PASS (wrote `src/compositions/Cover.tsx`).

## ENV-LIMITED detail

- **search_assets** — clean error: `OPEN_EDIT_PEXELS_API_KEY is not set; set it to search Pexels video, or pass a license=... filter to use Openverse` (expected).
- **generate=visual (full args)** — render sandbox lacks `moviepy`: `render sandbox failed (exit 1)` / `ModuleNotFoundError: No module named 'moviepy'` in `/workdir/_render_code.py`; structured error returned by MCP.
- **trigger_render proxy/cpu/wait=true** — `{"ok": false, "error_code": "render_failed", "error": "remotion materialize failed for UID '78d3a317-0892-4a57-86b2-0dd445d50d1c' ('Cover'): {\"ok\":false,\"error\":\"remotion produced no output file\"}"}` — root cause: Remotion needs Chrome Headless Shell; host has no browser cache and the remotion.dev download failed. Graph contained the matrix-required `generate=remotion` op.

## Notes / observations

- Generate ops use the `generate` / `generate_params` envelope (`edit_project` schema); passing them as `operation` returns a clean `unknown operation: 'X'` error.
- `generate=remotion` appended `Cover` composition, but the scaffolded `Root.tsx` only registers `TitleCard`; materialization never reached that check (blocked by missing browser).
- Background render (wait=false) returns a job_id, but the job is cancelled when the stdio server process exits (CancelledError path in render_jobs._run) — background jobs do not survive the driver process.
- `add_hyperframes_overlay` used `overlays/test.html` (trivial `<div>title</div>`, created in scratch project per instructions; `brand_lower_third.html` only exists in `testrun/project/overlays`).
- `replace_clip_source` / `apply_silence_gaps` were exercised on a re-added clip because matrix order runs `remove_clip` first (removed clip is gone from the timeline).
- init: `open_edit.cli init` requires the target folder to already exist (else `error: ... is not a directory`).
