# OpenEdit E2E — Confidence Audit Round 1 (CONFIDENCE_R1.md)

Auditor: confidence-orchestrator (round 1) · Rubric: testrun/ACCEPTANCE.md (sections A–E)
Date: 2026-08-06

## STRUCTURAL NOTE (delegation deviation)
This round was specified as "orchestrator + 6 child analysts". Spawning children via
`rlm()` is HARD-BLOCKED in this environment: RLM_DEPTH=1, RLM_MAX_DEPTH=1 (env
`RLM_MAX_DEPTH=1`; no kernel host handler exists to raise it). The orchestrator therefore
executed the six analyst areas (deliverables_video, report_docs, edit_graph_evidence,
tool_matrix, quality_spotchecks, pipeline_purity) itself, with the same standard demanded
of children: every item verified by direct, independent checks on raw artifacts
(ffprobe/ffmpeg/astats/DB queries/log parsing/pixel analysis/pytest), never by trusting
STATE.md, REPORT.md, TOOL_MATRIX.md, or AUDIT.md claims. Evidence below is the auditor's own.

## VERDICT: 100% confidence — VERDICT: PASS (0 concerns)

## Per-item table

| Item | Verdict | Evidence (auditor's own checks) |
|---|---|---|
| A1 | PASS | artifacts/openedit_demo_final.mp4 exists (22,812,944 B). ffprobe: h264 High 1920x1080 yuv420p, 30/1 fps, 863 frames; audio aac LC 48 kHz stereo; duration 28.766667 s (in 15–45 s); container mov,mp4 valid (probe_score 100). |
| A2 | PASS | `ffmpeg -v error -i <mp4> -f null -` exit 0, zero stderr lines. astats: RMS level −23.25 dBFS (> −50 → audible), peak −4.69 dBFS. |
| A3 | PASS | QC gate report for final render stored in render_jobs.db job 91b2cad3: complete=true, passed=true, policy=full, 10/10 checks passed (render_completed, proxy_render, streams, duration 28.77 vs 28.59 diff 0.18 < 1.0, audio_sync diff 0.001 < 0.2, black_frames 0, frozen_frames 0, silence 0, overlays_burned informational, thumbnail). Earlier QC-failed render (job 9fef3d81, 5 frozen intervals) documented and superseded by the passing re-render. |
| A4 | PASS | REPORT.md (27,690 B) covers: tools tested; 6 bugs found+fixed with file/line refs — 8/8 referenced locations verified to exist in source (validate.py:220-229, html_overlay.py:154, pyagent_generate_visual_for_segment.py:32-38, pyagent_timeline_ops.py:72-88, pipe_builder.py:100-112, emitter.py:240-255+280-340, tests/test_render_emitter.py:320-330); pipeline flow; reproduction steps; artifact paths. |
| A5 | PASS | TOOL_MATRIX.md (36 rows: 30 PASS / 3 ENV-LIMITED / 2 FAIL / 1 SKIP) lists all 6 MCP tools with PASS/FAIL + result snippets; every row mapped to a real mcp_calls.jsonl entry (scratch_proj log, 48 entries, verified row-by-row). |
| B1 | PASS | edit_graph.db (57 applied edits): add_clip 25, remove_clip 9, add_effect 7 (all color_grade, params contrast/gamma/saturation), add_html_overlay 2 (brand_lower_third + caption_sequence), set_audio_gain 11, replace_clip_source 3. Final timeline snapshot (hash 0c4bbbb617bcfcb1, rev 57): v1 video track = 10 clips (9 distinct cut boundaries), a1 = music bed (1 clip, −6 dB), a2 = 5 SFX clips. Cut ops = apply_silence_gaps splits (4 ops → 10 clips) + remove_clip. |
| B2 | PASS | project mcp_calls.jsonl (72 entries): query_project 16, edit_project 47 (add_clip 15, apply_silence_gaps 4, auto_color_grade 1, add_html_overlay 2, set_audio_gain 11, remove_clip 5, replace_clip_source 3), trigger_render 9 (final: ok=true, mode=final, output renders/project_0c4bbbb617bc.mp4, qc_passed=true). get_render_job exercised in scratch_proj log (5 calls incl. real job record); job lifecycle also fully recorded in render_jobs.db. Note (non-blocking): get_render_job calls live in the tool-matrix log, not the final project log. |
| B3 | PASS | renders/project_0c4bbbb617bc.mp4 (22,812,944 B) + project_0c4bbbb617bc.mlt (8 CAS producers, 3 playlists, 1 tractor, root `producer="tractor0"`); render_jobs.db job 91b2cad3: mode=final, status=succeeded, ok=true, elapsed 23.96 s, graph_revision 57, edit_graph_hash 0c4bbbb617bcfcb1…, output path = the render file. |
| B4 | PASS | Word-level alignment in every video take's asset meta.json: take1 17 words, take2 14, take3 20, take4 16 (each word: t_start/t_end/confidence/speaker). get_transcript_packed: query_project entries 9–12 returned real packed transcripts with timestamps + silence markers for 4 takes. get_silence_gaps: entries 1,4–7 returned real gaps/fillers (t_start/t_end/kind/text). |
| C1 | PASS | scratch_proj mcp_calls.jsonl: query_project 8, edit_project 29, run_script 3, trigger_render 2, get_render_job 5, cancel_render_job 1 — all 6 tools ≥ 1 call. |
| C2 | PASS | auto_color_grade: 1 call ok (applied 7 color_grade effects w/ params); apply_silence_gaps: 4 calls ok (snap splits, keep_count + new_clip_ids); get_silence_gaps: real gap/filler data returned; get_timeline_view: 2 calls ok (image exists 204,137 B valid PNG 1920×540); auditor's own timeline_view render on the render output is byte-identical (md5 034635a8…). |
| C3 | PASS | FAIL rows fixed w/ re-verify evidence: generate=visual — raw KeyError replaced by clean `missing required args: asset_hash, beat_type, template` + `expected_keys` (project log entries 59/70); write_remotion — clean validation error + happy path PASS (bytes 99, status ok). ENV-LIMITED rows have clean structured errors + documentation: search_assets (OPEN_EDIT_PEXELS_API_KEY not set), generate=visual full-args (sandbox moviepy — now installed in venv, v2.1.2), trigger_render remotion (Chrome headless shell unavailable). No silent failures. |
| C4 | PASS | Auditor ran the full suite as documented (venv activated): `python -m pytest tests/ -q --timeout=120 -p no:cacheprovider` → EXIT=0, 1474 tests, 0 failed, 7 skipped (exactly 1467 passed + 7 skipped). Logs: testrun/logs/pytest_r1_venv.log, pytest_r2.log. Note (non-blocking, env): running pytest WITHOUT venv activation makes 7 CLI tests fail because a stale console script /home/amr/.local/bin/open_edit (shebang /usr/bin/python) shadows the venv one; the documented command activates the venv and passes. |
| D1 | PASS | Auditor's own runs: ffprobe (streams/format above); `ffmpeg -v error` full decode exit 0; astats loudness (RMS −23.25, peak −4.69); own timeline_view render via build_timeline_view on renders/project_0c4bbbb617bc.mp4 → valid PNG 1920×540, 204,137 B (byte-identical to mission's); full test suite run twice (exit 0). |
| D2 | PASS | Frames at t=2,7,13,18,26: mean abs diffs 103.6 / 90.6 / 102.4 / 93.9 (≫ 1.0 → no frozen frames); no black frames (mean brightness 98–125, std 76–108). No clipping: astats max −4.69 dB < −1. QC on final render: 0 black spans, 0 frozen intervals, 0 silent gaps. |
| D3 | PASS | 10 video clips → 9 distinct cut points (≥3). Color grade: 7 avfilter.eq effects in MLT + auto_color_grade op. Overlay: authored (2 add_html_overlay) AND burned — auditor pixel evidence: orange #FF5A00 (RGB 255,90,0, tol ±30) pixels at t=1.5 (3304 px, mean RGB 247/92/8), t=10 (11,932 px), t=20 (729 px, mean RGB 253/89/1, bbox y[874–981] = lower third). Music/sfx mixed: a1 music bed (gain −6 dB) + a2 5 SFX clips in MLT; final audio stream present. |
| D4 | PASS | Provenance: artifact MD5 6df8fdd3… == renders/project_0c4bbbb617bc.mp4 (byte-identical); artifact mtime 04:42:09 = 25 s after render job 91b2cad3 completion (04:41:46); job record ok=true with QC attached and edit_graph_hash 0c4bbbb617bcfcb1 matching the timeline snapshot; render_cache key/meta tie output to hyperframes=0dedd9bc…|source-repair-v5-eo-overlay. Overlay mechanism: hyperframes/out/final/overlay_0dedd9bc04792f219f579931.mov (ProRes 1920×1080 yuva444p12le, 858 frames) composited by the OpenEdit pipe builder (bug #5 fix: [vfin]format=yuv420p[vout]); overlay pixels verified present in final artifact (see D3) — the QC `overlays_burned` "not requested in this render mode" line is informational only and does NOT indicate absence. No bypass: no ffmpeg concat anywhere in logs (run_script calls were benign sandbox prints); final video is the render job's output. |

## Concerns

NONE. Verdict threshold (100%, zero unresolved concerns) is met.

## Informational notes (explicitly NOT gate concerns; nothing to fix for acceptance)

1. Delegation deviation (environmental): RLM_MAX_DEPTH=1 blocked spawning the 6 child analysts; the six areas were executed inline by the orchestrator with direct evidence. If the parent requires the literal child topology, re-run with RLM_MAX_DEPTH≥2.
2. AUDIT.md (render-auditor) note 2 claims the overlays are "NOT visible in the final video pixels". This is contradicted by the auditor's direct pixel evidence (orange #FF5A00 accents at t=1.5/10/20). AUDIT.md is stale on this point; the video itself is correct.
3. get_render_job calls are recorded in scratch_proj/.open_edit/mcp_calls.jsonl (tool-matrix log), not in the final project's mcp_calls.jsonl; job lifecycle is additionally in render_jobs.db.
4. renders/project_b77638c3c0fa.mp4 is a 0-byte leftover from the bug #4 episode (documented in REPORT.md) — not part of the deliverable.
5. pytest requires the venv activated (`source .venv/bin/activate`) because a stale /home/amr/.local/bin/open_edit console script shadows the venv one otherwise; the documented reproduction command does this and passes.

VERDICT: PASS
