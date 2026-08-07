# Render Performance - Final Synthesis & Implemented Fixes (goal 151a2e42)

## The question
Why did a 37-min proxy preview take ~12 min (700.8s) when Premiere/DaVinci do ~1 min?

## The answer (measured)
700.8s = 77.9s CUDA video pass (11%) + 19.3s audio (3%) + **579.1s source-repair whole-file CPU re-encode (83%)** + ~25s mux/QC.
Three structural defects:
1. **R1 - Source repair**: proxy renders ran the full repair machinery; this source has 18 black + 16 frozen spans -> every render re-encoded the ENTIRE output through a Python raw-frame loop + libx264 CPU. 579s.
2. **R2 - Self-defeating cache**: default 1 GiB cap < 1.1 GB proxy output -> put() then evict() deleted the entry -> every render was a full miss (cache_hit=false in ALL jobs).
3. **R6 - Audio re-encoded every render**: the mux ran native-AAC (twoloop) over the 424 MB wav every time (~40s) with no cache.

## The fixes (implemented + verified in this session)
| Fix | File | Effect |
|---|---|---|
| Verify-based repair for previews (v6 policy: previews skip detect+re-encode; OPEN_EDIT_REPAIR opt-in) | render/source_repair.py, orchestrator.py | 579s -> ~0s |
| NVENC repair for final exports (was libx264 CPU) | render/source_repair.py | final repair faster |
| Segment-local repair machinery (windows only) | render/source_repair.py | final exports localize |
| Cache cap 1 GiB -> 32 GiB + protect-just-written entry from eviction | render/cache.py | identical re-render 700s -> 3s |
| faststart + 1s GOP on proxy/preview encodes | render/cuda_fastpath.py | first frame <100ms (moov 94% -> 0%), scrub <=1s |
| Source-proxy (360p) used for review-artifact renders (source_media_policy=proxy) | render/timeline_plan.py | video pass 78s -> 18s (122x) |
| Wav cache keyed by graph hash | orchestrator.py | melt-audio 19.3s -> 0s on re-render |
| NEW: AAC cache + fast coder (encode once per graph, mux -c:a copy) | orchestrator.py (encode_audio_aac_cache), cuda_fastpath.py | mux AAC 40s -> 0s after first; fresh encode 40s -> 12.3s (fast coder) |
| Regression tests | tests/test_render/test_audio_aac_cache.py (3 tests) | green |

## Verified benchmarks (RTX 4050 laptop, 37-min 1080p source, proxy 640x360)
| Scenario | Before | After |
|---|---|---|
| Fresh proxy render | 700.8s | ~34s (first AAC encode) |
| Same graph, new params | 700.8s | 23.6s |
| Identical re-render | 700.8s | 3.0s (cache hit) |
| First frame | moov at 94.3% (62 MB tail) | moov at 0.0% (faststart) |
| Scrub | 3.1 s median GOP | 1.0 s GOP |
| Output size | 1.1 GB | ~600-700 MB (crf-param dependent) |
| Test suite | - | 1500 passed / 0 failed / 10 env skips |

**Bottom line: preview-after-edit ~23-34s for a 37-min video (20-30x faster), identical re-render ~3s (233x), first frame <100ms.** The 1-minute target is met with margin. Remaining wall time is dominated by the video pass itself (17.6s @ 122x) which is decode/encode-bound.

## Not yet implemented (documented in PERF_MODPLAN.md, future work)
- Parallel segment rendering (preview-chunks pool, adaptive chunk size)
- Ingest-time source proxy auto-enqueue + UI wiring for preview-chunks
- Keyframe index endpoint + scrub snapping in the UI
- Lightweight state endpoint (delta polls) + render progress columns
- Thumbnail strip + waveform caches
