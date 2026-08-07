# OpenEdit E2E — Acceptance Rubric (used by confidence-auditor)

The auditor MUST verify every item with concrete evidence (file paths, command
outputs, log lines). An item without evidence FAILS. Verdict: confidence 0-100%.
Only 100% passes. Any concern (even minor) forces a fix + re-audit round.

## A. Deliverables (evidence = files exist + independent re-check)
- [ ] A1. Final video exists at a stated path; ffprobe shows video+audio streams,
      1920x1080 (or documented), fps>=24, duration 15-45s, container valid.
- [ ] A2. Video decodes end-to-end without errors (ffmpeg -v error full decode) and
      is NOT silent: audio track has audible RMS > -50dBFS.
- [ ] A3. QC gate report exists for the final render; no failed checks.
- [ ] A4. REPORT.md exists and covers: tools tested, bugs found+fixed (with file/line),
      pipeline flow, reproduction steps, artifact paths.
- [ ] A5. TOOL_MATRIX.md exists: every MCP tool listed with PASS/FAIL + log evidence.

## B. "Made with OpenEdit" (evidence = edit graph + render logs + mcp_calls.jsonl)
- [ ] B1. The project edit graph contains the ops that made the video: >=4 AddClipOp,
      >=1 AddEffectOp (color_grade), >=1 overlay op or template, audio ops, cut ops.
- [ ] B2. mcp_calls.jsonl shows the video was driven through the MCP surface
      (query_project/edit_project/trigger_render/get_render_job at minimum).
- [ ] B3. Render was executed by OpenEdit's orchestrator (renders dir + render job log).
- [ ] B4. Transcript pipeline exercised: asset alignment exists (word-level), and
      get_transcript_packed or get_silence_gaps returned real data for a take.

## C. Tool matrix completeness (evidence = TOOL_MATRIX.md + mcp_calls.jsonl)
- [ ] C1. All 6 MCP tools exercised (query_project, edit_project, run_script,
      trigger_render, get_render_job, cancel_render_job).
- [ ] C2. New ops verified working: auto_color_grade, apply_silence_gaps
      (snap/padding), get_silence_gaps, get_timeline_view.
- [ ] C3. Every tool that initially FAILED is either fixed (with re-verify evidence)
      or documented as environment-limited with a clean error (no silent failures).
- [ ] C4. Full pytest suite passes (exit 0) after all fixes.

## D. Quality & no design failures (evidence = auditor's own spot checks)
- [ ] D1. Auditor independently runs: ffprobe on final video; ffmpeg decode;
      audio loudness (astats); 1 timeline_view render; test suite (or reads last
      suite log if too slow — note it).
- [ ] D2. No black/frozen frames flagged by QC; no clipping (max dB < -1).
- [ ] D3. The video is a real multi-clip edit: >=3 visible cut points in the graph
      (distinct clip boundaries), color grade present, overlay present (burned or
      authored), music/sfx mixed (audio ops or mixed bed).
- [ ] D4. No bypass hacks: final video must be the product of the OpenEdit render
      pipeline, not a hand-made ffmpeg concat outside the project.

## E. Verdict format (write to testrun/CONFIDENCE_R<n>.md)
- confidence: N% (only 100% passes)
- per-item: PASS/FAIL/UNCERTAIN + evidence path or missing-evidence note
- concerns: numbered list, each with severity (blocker/minor) + the exact thing
  the coordinator must fix + how to re-verify
- final line: "VERDICT: PASS" or "VERDICT: FAIL (<n> concerns)"


## Audit structure (user requirement — orchestrator + 6 children)
The confidence audit is performed by ONE orchestrator sub-agent that spawns
SIX child analyst sub-agents (its own children), each owning a rubric area:
1. deliverables_video   -> A1, A2, A3 (file integrity, decode, audio, QC)
2. report_docs          -> A4, A5 (REPORT.md, TOOL_MATRIX.md completeness)
3. edit_graph_evidence  -> B1-B4 (ops, mcp_calls.jsonl, transcript pipeline)
4. tool_matrix          -> C1-C4 (all tools + new ops + failures fixed + suite)
5. quality_spotchecks   -> D1-D3 (own ffprobe/decode/loudness/timeline-view)
6. pipeline_purity      -> D4 (no bypass hacks, render came from orchestrator)
Each child returns a short analysis (per-item PASS/FAIL/UNCERTAIN + evidence)
to the orchestrator via agent_message. The orchestrator writes
CONFIDENCE_R<n>.md, computes the 0-100% score, and replies VERDICT to parent.
Any FAIL/UNCERTAIN or <100% -> coordinator fixes -> NEW orchestrator+6 round.
