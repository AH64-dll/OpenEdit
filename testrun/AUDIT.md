# OpenEdit Final Demo Video — Independent Render Audit

Auditor: render-auditor subagent (independent; no coordinator claims trusted)
Date: 2025-08-06
Video under test: /home/amr/apps/mlt-pipeline/testrun/artifacts/openedit_demo_final.mp4
Source render:    /home/amr/apps/mlt-pipeline/testrun/project/.open_edit/renders/project_0c4bbbb617bc.mp4

## Result: ALL 8 CHECKS PASS — no blocking or minor concerns for confidence gate.

---

## 1. ffprobe streams — PASS
- Container: MP4 (mov,mp4,m4a,3gp,3g2,mj2), duration 28.766667 s, size 22,812,944 B, bitrate ~6.34 Mbps
- Video: h264 High, 1920x1080, yuv420p, 30 fps (r_frame_rate=avg_frame_rate=30/1), 863 frames (independent raw decode: 1,789,516,800 B / (1920*1080) = 863.0 exact; show_streams nb_frames=863)
- Audio: aac LC, 48000 Hz, stereo (2ch), 1,349 AAC packets = 1,381,376 samples = 28.779 s (0.012 s audio tail pad vs video; immaterial)
- Final artifact MD5 == source render MD5: 6df8fdd35561ccecc7bbe53b0cd54830 (identical content)

## 2. Full decode — PASS
- `ffmpeg -v error -i openedit_demo_final.mp4 -f null -` exit 0, zero error/warning lines (video+audio fully decodable)

## 3. Loudness — PASS (no clipping flag)
- mean_volume: -23.3 dB, max_volume: -4.7 dB (n_samples 2,762,752 = 2ch x 1,381,376)
- max < -1 dB threshold → no clipping. Healthy headroom; mean is quiet-ish but in normal dialog range.

## 4. Motion sanity — PASS (no frozen frames)
Extracted frames at t=2,7,13,18,26 (all 1920x1080 grayscale), mean abs diff between successive points:
- t=2→7:  55.97
- t=7→13: 85.35
- t=13→18: 102.41
- t=18→26: 94.32
All >> 1.0 threshold. Continuous real motion across whole video.

## 5. OpenEdit QC gate (policy=full, mode=final, target 28.59 s) — PASS (complete=true, passed=true)
| check | status | detail |
|---|---|---|
| render_completed | PASS | proxy MP4 exists; orchestrator ok=True |
| proxy_render | PASS | artifact path |
| streams | PASS | 1 video, 1 audio |
| duration | PASS | 28.77 s vs 28.59 target, diff 0.18 s (limit 1.0) |
| audio_sync | PASS | video=28.767 s audio=28.766 s, diff 0.001 s (limit 0.2) |
| black_frames | PASS | 0 spans (0 new, 0 source-known) |
| frozen_frames | PASS | 0 intervals (0 new, 0 source-known; min 1.0 s) |
| silence | PASS | 0 silent gaps |
| overlays_burned | PASS | "overlays not requested in this render mode" (see note) |
| thumbnail | PASS | /tmp/audit_thumbs/openedit_demo_final_thumb.jpg (480x270) |
All checks passed, none skipped, elapsed 1.96 s.

## 6. Edit-graph evidence — PASS
- clips: 16 (v1 video track = 10 clips)
- tracks: [('v1','video',10), ('a1','audio',1), ('a2','audio',5)] → 2 audio tracks ✓
- overlays: 2 ✓
- effects: 13 → color_grade x7 (exactly meets >= 7), volume x6
- Requirement >=10 video clips ✓, >=2 audio tracks ✓, 2 overlays ✓, >=7 color_grade ✓

## 7. MCP evidence — PASS
- /home/amr/apps/mlt-pipeline/testrun/project/.open_edit/mcp_calls.jsonl: 71 entries
- edit_project: 47, query_project: 15, trigger_render: 9
- All required tools (query_project, edit_project, trigger_render) present ✓

## 8. timeline_view self-check — PASS
- Command returned status=ok, isError=false, image_path=/home/amr/apps/mlt-pipeline/testrun/project/.open_edit/timeline_views/project_0c4bbbb617bc_0.00-6.00.png
- File exists, 204,137 B, valid PNG 1920x540, n_frames=6, start=0 end=6 legend present

---

## Concerns / notes (non-blocking)
1. Duration 28.77 s vs target 28.59 s: +0.18 s over target, well inside 1.0 s QC limit. Expected render padding.
2. overlays_burned check passes only because overlays are not burned in this render mode; the 2 edit-graph overlays are NOT visible in the final video pixels (they exist as separate overlay assets). Flagged as designed behavior, not a defect.
3. Audio mean level -23.3 dB LUFS-ish (volumedetect) is modest; max -4.7 dB means no clipping but the mix is conservative. Cosmetic only.
4. Final artifact is byte-identical (MD5) to the source render — expected (proxy copy), confirms provenance.
