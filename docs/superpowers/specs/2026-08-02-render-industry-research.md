# Open Edit — Industry Renderer Research (Phase 2 Tier 1 + Phase 4)

> **Role:** Open-Source Renderer Researcher  
> **Date:** 2026-08-02  
> **Status:** Research only. No `open_edit/` code changes.  
> **Grounded on:** `docs/superpowers/specs/2026-08-02-render-ground-truth.md`,  
> `docs/superpowers/plans/open-edit-rendering-optimization-plan.md`  
> **Evidence policy:** Tier 1 claims cite docs/source/commits. Tier 2 labeled **“reported by X, unverified.”**

---

## 0. Open Edit baseline (Phase 0 facts this research maps onto)

| Fact | Implication for industry mapping |
|---|---|
| `mode=proxy` = full-timeline melt→ffmpeg MP4 encode (same spine as final, cheaper profile) | “Make proxy faster” alone never yields Kdenlive/Shotcut scrub feel |
| Review Studio plays HTML5 `<video>` of that MP4 — **no** live MLT SDL/OpenGL consumer | Interactive scrub is a **product gap**, not a profile tweak |
| Remotion materialize runs before melt; per-comp cache exists | Effect-heavy cost is often **pre-baked overlays**, not MLT filters |
| Main render jobs = **host worker** (`open_edit.cli render`); free-form IR = **bwrap/ops.jsonl** | GPU/preview proposals must state worker vs sandbox |
| Disk already stressed (timeline-test ~95%) | Any chunk/proxy cache needs eviction + size caps |

Three industry systems (plan § Orchestrator review):

1. **Source proxies** — low-res stand-ins for heavy camera media  
2. **Timeline preview cache** — chunked background bake of dirty zones  
3. **Final export** — full-quality deliverable  

Open Edit today has (3), a misnamed (1)/(2) hybrid as whole-file output proxy, and **no** interactive consumer.

---

## 1. Kdenlive — timeline preview chunks + invalidation (Tier 1)

### 1.1 What it is

Kdenlive’s **Timeline Preview Rendering** (since 16.08) background-renders selected timeline **zones** so playback/scrub of effect-heavy regions stays realtime. Explicitly: it speeds **playback**, not edit operations.

**Primary source:** [Timeline Preview Rendering — Kdenlive Manual 26.04](https://docs.kdenlive.org/en/tips_and_tricks/tips_and_tricks/timeline_preview_rendering.html)

### 1.2 Chunk model

| Property | Evidence |
|---|---|
| Chunk size | Manual: **25 frames** per chunk (1 s @ 25 fps). Settings expose `timelinechunks` (UI/ruler use `KdenliveSettings::timelinechunks()`). |
| Progress UX | Red → yellow → green bar between ruler and top track, **chunk by chunk** |
| Zones | User sets I/O, **Add Preview Zone**; multiple non-contiguous zones allowed |
| Output | Separate video files per chunk under project cache; purge via Project Settings → Cache Data |

### 1.3 Invalidation rules (critical)

From the same manual:

- Preview covers **video only**. **Audio is always independent** — audio edits do **not** invalidate video preview chunks.
- Any change to video (clips/transitions) that **touches** a preview zone **stops** background render and marks affected chunks **red** (dirty). User restarts render.
- Smart undo/redo: limited undo levels can **restore** previously rendered chunks without re-bake (PreviewManager archives undo levels of preview files).
- Desync escape hatch: remove zone(s) → re-add → re-render.

Phabricator T1949 (feature design) and PreviewManager commits confirm architecture:

- Background process writes N-frame chunk files.
- Playback uses a temporary **overlay track** on the MLT tractor (`buildPreviewTrack` / `setOverlayTrack` / `m_overlayTrackCount` in [`timelinemodel.hpp`](https://github.com/KDE/kdenlive/blob/master/src/timeline2/model/timelinemodel.hpp)).
- Render engine mode `preview-chunks` in [`kdenlive_render.cpp`](https://github.com/KDE/kdenlive/blob/master/renderer/kdenlive_render.cpp): loads MLT XML playlist, iterates chunk frame lists, writes avformat consumer outputs into a cache directory.
- Refactor commit: [PreviewManager class (2c51113e)](https://invent.kde.org/multimedia/kdenlive/-/commit/2c51113e238044f36d587749e868af0f79b4c7c9) — `invalidatePreviews`, undo archive, cleanup of old preview levels.
- Preview enable/disable + overlay: [5f9e4351](https://invent.kde.org/multimedia/kdenlive/-/commit/5f9e4351f2756d738fe9517043d502af1830ed34); render CLI alignment: [1f67f8cd](https://invent.kde.org/multimedia/kdenlive/-/commit/1f67f8cd56ed987bca4b864a9290fc2542b1eb64).

T1949 note (Jean-Baptiste Mardelle): overlay-track chunks beat per-clip pre-render for **transitions/composites**; per-clip proxies alone cannot guarantee smooth multi-track playback.

### 1.4 Proxies ≠ timeline preview

[Proxy Settings — Kdenlive Manual](https://docs.kdenlive.org/en/project_and_asset_management/project_settings/proxy_settings.html):

- Proxies = reduced source stand-ins for editing; replaced by originals at **full render**.
- Default proxy width **640px**; auto-generate for videos wider than threshold.
- Manual stress-test: proxies **do not** help when effects (defish, grade, sharpen) make even HD realtime fail — that is what **timeline preview** is for.

### 1.5 Architecture stay-in-MLT

[dev-docs/architecture.md](https://github.com/KDE/kdenlive/blob/master/dev-docs/architecture.md): Kdenlive UI + **MLT** for decode/compose/render. Preview is not a second compositor — it is **MLT delivery + avformat chunk bake + tractor overlay**.

---

## 2. Shotcut — preview scaling, proxies, HW decode (Tier 1)

### 2.1 Preview scaling

**Primary:** [Settings > Preview Scaling (Shotcut forum docs)](https://forum.shotcut.org/t/settings-preview-scaling/15650), [v20.02 release](https://shotcut.org/blog/new-release-200217/)

- Reduces **processing** resolution while editing (filters/transitions/blend), not just display.
- Vertical options: 360p / 540p / 720p (width follows project DAR).
- Export → Advanced → **Use preview scaling** = fast draft export (analogous to Open Edit `mode=proxy` intent).
- Caveat: Stabilize filter disables preview scaling; not full WYSIWYG for blur/noise.

**MLT-native mechanism:** [MLT Preview Scaling docs](https://www.mltframework.org/docs/previewscaling/) (since MLT 6.20): dual profiles (full graph profile + lower-res consumer profile), or consumer `scale=` for melt. Same-scale width/height recommended; some filters suppress scaling.

### 2.2 Proxy editing

**Primary:** [Settings > Proxy Editing](https://forum.shotcut.org/t/settings-proxy-editing/18517)

| Rule | Detail |
|---|---|
| Goal | Less decode/scale/effects work via fewer pixels; export swaps back to originals |
| Pairing | **Optimal when proxy vertical res == Preview Scaling** |
| Generation | Jobs queue; async Replace of clips; continue editing originals until ready |
| Skip rules | No alpha, no image sequences, dimensions ≤1.3× preview scale, etc. |
| Draft export | Preview scaling ON → export may keep proxies for rough review |
| HW encode for proxies | Optional; lead: often little win at low res; HEVC if HW used |

Forum clarification ([Austin on Proxy vs Preview Scaling](https://forum.shotcut.org/t/difference-between-preview-scaling-and-proxy/34728/10)):

- **Proxy** → faster **decode**  
- **Preview Scaling** → cheaper **frame processing**  
- Together at matched res = “golden path” (no wasteful scale steps)

### 2.3 Hardware decode caveats (v26.1)

**Primary:** [Shotcut 26.1 release notes](https://shotcut.com/blog/new-release-26.01.30/), [FAQ — How does Shotcut use the GPU?](https://www.shotcut.org/FAQ/)

- Preview HW decode: Settings → Preview Scaling → Use Hardware Decoder; default ON except **NVIDIA on Linux** (VA-API / MF / VideoToolbox).
- **Does not help scrubbing much — proxies still key.**
- **Not 0-copy** with GPU processing mode; CPU↔GPU transfer limits value → capped at preview scale or ≤1080p60 (`MLT_AVFORMAT_HWACCEL_PPS=0` to override).
- FAQ: full zero-copy GPU pipelines are hard; if frames bounce CPU↔GPU, gains evaporate. Prefer not chasing vendor-locked CUDA-only pipelines.
- Export HW **decode** defaults OFF (can **increase** export time).

### 2.4 Interactive consumer (contrast to Open Edit)

Shotcut **is** an interactive MLT app (SDL/OpenGL display path + MLT consumer). Open Edit Review Studio is **not**. Copying Shotcut’s scrub feel requires either (a) a live consumer path, or (b) a chunked cache that HTML5 can seek without full re-encode — not only Shotcut’s preview-scale export checkbox.

---

## 3. Other Tier 1 editors (patterns, not blueprints)

### 3.1 Olive Video Editor

- [0.2 Quickstart — Caching](https://github.com/olive-editor/olive/wiki/Olive-0.2.x-Quickstart): disk pre-render of sequence portions as **small images** so unchanged regions replay without recompute; prefs + per-project cache path.
- [Design Architecture DAG](https://github.com/olive-editor/olive/wiki/Design-Architecture-DAG): playhead TC flows through graph; top channel writes image cache.
- Compositing historically OpenGL/GLSL ([issue #633](https://github.com/olive-editor/olive/issues/633)) — **leaves MLT**; useful as UX parallel (disk frame cache), not as stack replacement for Open Edit.

### 3.2 OpenShot / libopenshot

- [`VideoCacheThread`](https://www.openshot.org/static/files/libopenshot/classopenshot_1_1VideoCacheThread.html): high-priority thread maintains a **sliding window** of frames around the playhead (ahead/behind, seek reset, preroll). **RAM** prefetch for live player — not durable chunk files.
- OpenShot uses its own libopenshot timeline (ffmpeg-based), not MLT. Pattern transferable only if Open Edit gains a live frame server.

### 3.3 Blender VSE

- [Proxy](https://docs.blender.org/manual/en/latest/editors/video_sequencer/sequencer/sidebar/proxy.html): per-strip / project proxy dirs; multi-resolution; Rebuild Proxy + Timecode; preview picks Proxy Render Size; final uses full.
- [Cache](https://docs.blender.org/manual/en/latest/editors/video_sequencer/sequencer/sidebar/cache.html): **RAM** cache of raw vs final composited frames; Prefetch Frames; Show Cache overlay (red/blue bars); memory cap in Preferences.
- Closest Open Edit mapping: **source proxies + memory/disk preview cache visualization**; Blender’s interactive VSE viewer ≠ Review Studio HTML5.

### 3.4 Natron

- [Preview and rendering](https://natron.readthedocs.io/en/v2.4.2/guide/compositing-projects-render.html): viewer proxy quality; play fills **memory cache** then loops realtime.
- [DiskCache node](https://natron.readthedocs.io/en/v2.3.15/plugins/fr.inria.built-in.DiskCache.html) + [caching guide](https://github.com/NatronGitHub/Natron/blob/RB-2.5/Documentation/source/guide/compositing-projects-caching.rst): bake a **branch** of the node tree to disk (full float frames); prefs for max GiB + path; wipe cache.
- Transferable idea: treat **Remotion materialize outputs** like a DiskCache branch — pin stable comps, invalidate only dirty UIDs (Open Edit already has per-comp keys; Natron reinforces **branch-level** bake + hard disk caps).

---

## 4. Tier 2 — UX targets only (unverified)

| System | Reported pattern | Label |
|---|---|---|
| Premiere Pro | Mercury Playback Engine GPU renderer for effects/scaling/playback; separate HW encode/decode | **Reported by Adobe HelpX / community FAQ, unverified** — [Enable MPE](https://helpx.adobe.com/premiere/desktop/get-started/technical-requirements/enable-mercury-playback-engine-gpu-accelerated-renderer.html). Use only as UX target: “scrub stays realtime after idle work.” |
| DaVinci Resolve | Smart/User caches at Source/Fusion, Node, and Sequence levels so grade edits ≠ timeline re-cache | **Reported by Resolve manual excerpts (VFXPedia mirror), unverified**. UX target: layered invalidation, not architecture copy. |
| Final Cut Pro | Background render / optimized media (anecdotal industry lore) | **Unverified** — do not drive Open Edit design. |

---

## 5. Patterns that map cleanly onto Open Edit **without leaving MLT**

Ranked for Open Edit’s actual gap (full MP4 proxy + Remotion + host worker + HTML5 review):

### Rank 1 — Chunked timeline preview cache + dirty-zone invalidation (Kdenlive)

| | |
|---|---|
| **What** | Background melt/avformat (or existing pipe) writes N-frame (or N-second) chunks for marked zones; invalidate only touched zones; audio independent |
| **Why #1** | Directly attacks “every edit → full timeline MP4”; matches Remotion-heavy dirty regions |
| **MLT fit** | Same as Kdenlive: emit MLT XML → `preview-chunks`-style jobs → files on disk. Can overlay in MLT **or** feed Review Studio via segment playlist / byte-range |
| **Worker** | Host render worker (already runs melt/ffmpeg) |
| **IR** | Soft: timeline-derived dirty intervals from Edit Graph ops (clip/comp time ranges). No ops.jsonl change required if Python derives dirty sets |

### Rank 2 — Separate audio path from video preview re-bake (Kdenlive)

| | |
|---|---|
| **What** | Mute/gain/cut audio without flushing video chunk cache |
| **Why** | Open Edit silence cuts / gain ops are frequent; today they still force full proxy hash miss |
| **MLT fit** | Preview video chunks silent or video-only; audio from live melt audio consumer or separate WAV (Open Edit already has melt audio side-path in pipe) |
| **Worker** | Host |
| **IR** | Cache key split: `video_preview_key` vs `audio_key` |

### Rank 3 — Source proxies ≠ `mode=proxy` (Shotcut / Kdenlive / Blender)

| | |
|---|---|
| **What** | Per-asset low-res CAS derivatives; emit timeline uses proxies for preview profiles; final swaps originals |
| **Why** | Clarifies naming; helps long 4K sources; **does not** alone fix Remotion overlay cost |
| **MLT fit** | Producer path points at proxy files; profile already 640×360-class |
| **Worker** | Host (proxy gen jobs like Shotcut Jobs panel) |
| **IR** | Asset metadata: `proxy_hash` optional; emission chooses hash by profile |

### Rank 4 — Matched preview scaling + source proxy resolution (Shotcut + MLT)

| | |
|---|---|
| **What** | Dual MLT profiles or consumer scale; proxies generated at same vertical res |
| **Why** | Avoids decode-full then scale-down waste; MLT documents the dual-profile pattern |
| **MLT fit** | Native; melt consumer `scale=` or second Profile |
| **Worker** | Host |
| **IR** | Profile registry only |

### Rank 5 — Overlay / replace dirty segment into review artifact (Kdenlive overlay track → HTML5 adaptation)

| | |
|---|---|
| **What** | Green chunks play from cache; red zones fall back to live lower-quality or prior proxy |
| **Why** | Review Studio can stay file-based initially: concatenate or Media Source Extensions / HLS of chunks — **without** shipping SDL into the browser |
| **MLT fit** | Chunk bake stays MLT; playback may stay HTML5 |
| **Worker** | Host |
| **IR** | Preview zone markers optional (pinned values / markers) |

### Rank 6 — Disk cache budget + purge UI (Kdenlive Cache Data / Natron prefs / Olive)

| | |
|---|---|
| **What** | Cap timeline-preview + Remotion out/ + render_cache; pie-chart / wipe |
| **Why** | Ground truth + ops memory: timeline-test disk crises |
| **MLT fit** | Orthogonal to MLT |
| **Worker** | Host |
| **IR** | None |

### Rank 7 — Remotion as Natron-style DiskCache branch

| | |
|---|---|
| **What** | Treat each composition materialize as a pinned branch cache; dirty UID only |
| **Why** | Phase 0 already has per-comp keys; industry validates branch bake |
| **MLT fit** | Remotion stays outside MLT; melt only sees CAS clips |
| **Worker** | Host Remotion CLI |
| **IR** | None if cache keys already graph-driven |

### Weaker fit (keep for later)

| Pattern | Source | Why weaker for Open Edit now |
|---|---|---|
| RAM sliding-window prefetch | OpenShot, Blender | Needs live frame consumer / continuous decode loop |
| Full OpenGL GPU compositor | Olive, Shotcut Movit mode | Leaves or heavily extends MLT; Shotcut itself warns on 0-copy |
| Live SDL2/qglsl consumer in Review Studio | MLT [sdl2](https://www.mltframework.org/plugins/ConsumerSdl2/), [OpenGL](https://www.mltframework.org/docs/opengl/) | Highest scrub fidelity; large product/architecture change (native viewer or WASM — not today’s HTML5 MP4) |

---

## 6. Phase 4 tech options (research)

Each option: sandbox vs host worker, integration cost, IR impact. Bias from plan: extend MLT+ffmpeg+Remotion unless Phase 1 proves the pipe is the ceiling.

### 6.1 Interactive MLT consumer (sdl2 / qglsl / custom frame pump)

| Axis | Assessment |
|---|---|
| **Sandbox vs host** | **Host worker / desktop process only.** Free-form bwrap must not share GL contexts. Review Studio today is browser — would need native preview window, local frame WS, or replace HTML5 path. |
| **Integration cost** | **High.** New long-lived process; seek/play protocol; Remotion overlays still need materialize or live WebVfx (deprecated/hard). Dual-profile preview scaling is the easy part ([MLT preview scaling](https://www.mltframework.org/docs/previewscaling/)). |
| **IR impact** | Low if consumer reads same emitted MLT XML. High if Review Studio product model changes. |
| **Verdict** | Correct long-term scrub UX; **not** first incremental step given HTML5 review. Prefer after/with chunked cache. |

### 6.2 Chunked preview cache (Kdenlive-style)

| Axis | Assessment |
|---|---|
| **Sandbox vs host** | **Host render worker** — same as `cli render`. Sandbox untouched. |
| **Integration cost** | **Medium.** New job type `preview-chunks`; cache dir + eviction; dirty interval from graph diff; Review Studio: playlist of chunk files or stitch on demand. Reuse melt→ffmpeg pipe at preview profile. |
| **IR impact** | **Low–medium.** Optional preview zones; cache keys = graph hash **sliced by time range** + Remotion fingerprints in range. Edit Graph ops already carry timing. |
| **Verdict** | **Best Phase 4 candidate** aligned with Tier 1 + ground truth. |

### 6.3 Source proxies (per-asset)

| Axis | Assessment |
|---|---|
| **Sandbox vs host** | **Host** proxy-generation jobs (ffmpeg/NVENC optional). |
| **Integration cost** | **Medium-low.** CAS sibling files; emitter prefers proxy producers for `proxy`/`preview` profiles; final uses originals. |
| **IR impact** | **Low.** Asset record fields; no Edit Graph semantic change. |
| **Verdict** | Do in parallel with chunks; rename product language so `mode=proxy` ≠ source proxy. Helps decode; **weak alone** for Remotion-heavy timelines (Kdenlive proxy docs). |

### 6.4 Hardware decode / encode paths

| Axis | Assessment |
|---|---|
| **Sandbox vs host** | **Host only** (NVENC/CUDA already on worker path per ground truth). |
| **Integration cost** | **Low for encode** (already present); **medium for decode** (`hwaccel=cuda` already optional). Shotcut: do not expect scrub miracles; watch NVIDIA+Linux VA-API defaults. |
| **IR impact** | None. |
| **Verdict** | Keep measuring (Phase 1). **Do not** invest in 0-copy GPU compositor until pipe+Remotion measured. Shotcut FAQ is explicit Tier 1 skepticism. |

### 6.5 Segmented review MP4 / HLS from chunks (HTML5-friendly)

| Axis | Assessment |
|---|---|
| **Sandbox vs host** | Host. |
| **Integration cost** | **Medium.** ffmpeg segment muxer or fMP4; Review Studio Media Source / HLS.js. Migration: keep whole-file proxy as fallback. |
| **IR impact** | None. |
| **Verdict** | Bridge between Rank 1 cache and current UI without live MLT in browser. |

### 6.6 Greenfield Vulkan/Metal compositor / zero-copy MLT↔ffmpeg

| Axis | Assessment |
|---|---|
| **Sandbox vs host** | Host; may conflict with Hard Constraints if anyone proposes GPU inside free-form sandbox. |
| **Integration cost** | **Very high.** Leaves proven melt→ffmpeg frame-server. |
| **IR impact** | Potentially large. |
| **Verdict** | **N/A** until Phase 1 proves pipe ceiling (plan Hard Constraints). |

### 6.7 OpenShot-style RAM window / Blender RAM final cache

| Axis | Assessment |
|---|---|
| **Sandbox vs host** | Host process holding frame buffers. |
| **Integration cost** | High without interactive consumer; with consumer, medium. |
| **IR impact** | Low. |
| **Verdict** | Secondary after live path exists. |

---

## 7. Mapping matrix — industry → Open Edit product split

| Industry system | Open Edit today | Recommended mapping |
|---|---|---|
| Interactive scrub | Missing (HTML5 MP4 only) | Chunk cache → HTML5 segments **or** later MLT consumer |
| Timeline preview cache | Missing (whole-file proxy closest) | Kdenlive chunks + dirty zones + audio split |
| Source proxies | Misnamed as `mode=proxy` | Per-asset CAS proxies + emission switch |
| Preview scaling | Profile `fast_proxy` 640×360 on **full encode** | MLT dual profile for live path; keep low-res for chunk bake |
| Final export | `mode=final` melt→ffmpeg + Remotion | Keep; Remotion DiskCache discipline + skip redundant QC |
| HW path | NVENC + optional cuda decode | Keep; heed Shotcut scrub caveat |
| Disk policy | Ad-hoc cleanup | Formal caps (Kdenlive/Natron) |

---

## 8. Top transferable patterns (ranked for Open Edit)

1. **Chunked timeline preview with zone invalidation** (Kdenlive docs + `preview-chunks` + PreviewManager) — primary answer to full-timeline MP4 invalidation.  
2. **Audio-independent video preview cache** (Kdenlive) — stop silence/gain edits from flushing video bake.  
3. **True source proxies separate from output proxy mode** (Shotcut / Kdenlive / Blender) — naming + decode cost.  
4. **Matched preview scale + proxy resolution** (Shotcut + MLT preview scaling) — avoid useless scale work.  
5. **Overlay/fallback playback of green vs red zones** (Kdenlive tractor overlay → adapt to HTML5 segments).  
6. **Hard disk cache budgets + purge** (Kdenlive Cache Data, Natron DiskCache prefs).  
7. **Branch/composition bake with dirty-only rematerialize** (Natron DiskCache analogy → Remotion cache).  
8. **HW decode skepticism for scrub** (Shotcut FAQ / v26.1) — measure; don’t bet architecture on 0-copy.  
9. **RAM playhead window** (OpenShot / Blender) — only after a live consumer exists.  
10. **Tier 2 layered Smart Cache UX** (Resolve, unverified) — inspiration for invalidation layers, not code.

---

## 9. Explicit non-recommendations (for Synthesis agent)

- Do **not** treat “faster full proxy MP4” as solving interactive preview (Phase 0).  
- Do **not** justify Vulkan/zero-copy from Premiere Mercury lore (**Tier 2, unverified**).  
- Do **not** put GPU interactive consumers inside free-form IR sandbox.  
- Do **not** expect source proxies to fix Remotion overlay wall-clock (Kdenlive: proxies ≠ effect bake).  
- Do **not** adopt Olive’s OpenGL stack as MLT replacement without Phase 1 proof.

---

## 10. Sources index

### Tier 1 — primary

- Kdenlive Timeline Preview: https://docs.kdenlive.org/en/tips_and_tricks/tips_and_tricks/timeline_preview_rendering.html  
- Kdenlive Proxy Settings: https://docs.kdenlive.org/en/project_and_asset_management/project_settings/proxy_settings.html  
- Kdenlive architecture: https://github.com/KDE/kdenlive/blob/master/dev-docs/architecture.md  
- Kdenlive `preview-chunks`: https://github.com/KDE/kdenlive/blob/master/renderer/kdenlive_render.cpp  
- PreviewManager commits: https://invent.kde.org/multimedia/kdenlive/-/commit/2c51113e238044f36d587749e868af0f79b4c7c9 , https://invent.kde.org/multimedia/kdenlive/-/commit/5f9e4351f2756d738fe9517043d502af1830ed34  
- T1949: https://phabricator.kde.org/T1949  
- Shotcut FAQ (GPU / HW decode limits): https://www.shotcut.org/FAQ/  
- Shotcut 26.1: https://shotcut.com/blog/new-release-26.01.30/  
- Shotcut Proxy Editing: https://forum.shotcut.org/t/settings-proxy-editing/18517  
- Shotcut Preview Scaling: https://forum.shotcut.org/t/settings-preview-scaling/15650  
- MLT Preview Scaling: https://www.mltframework.org/docs/previewscaling/  
- MLT OpenGL / sdl2: https://www.mltframework.org/docs/opengl/ , https://www.mltframework.org/plugins/ConsumerSdl2/  
- Olive caching: https://github.com/olive-editor/olive/wiki/Olive-0.2.x-Quickstart  
- OpenShot VideoCacheThread: https://www.openshot.org/static/files/libopenshot/classopenshot_1_1VideoCacheThread.html  
- Blender VSE Proxy / Cache: https://docs.blender.org/manual/en/latest/editors/video_sequencer/sequencer/sidebar/proxy.html , …/cache.html  
- Natron preview / DiskCache: https://natron.readthedocs.io/en/v2.4.2/guide/compositing-projects-render.html , https://natron.readthedocs.io/en/v2.3.15/plugins/fr.inria.built-in.DiskCache.html  

### Tier 2 — context only

- Adobe MPE help: https://helpx.adobe.com/premiere/desktop/get-started/technical-requirements/enable-mercury-playback-engine-gpu-accelerated-renderer.html — **reported by Adobe, unverified as architecture evidence**  
- Resolve cache organization (manual mirror): https://www.steakunderwater.com/VFXPedia/__man/Resolve18-6/DaVinciResolve18_Manual_files/part247.htm — **reported by Resolve docs mirror, unverified**

### Internal

- `docs/superpowers/specs/2026-08-02-render-ground-truth.md`  
- `docs/superpowers/plans/open-edit-rendering-optimization-plan.md`

---

## 11. Handoff notes

- **For Sandbox & IR Reviewer:** Rank 1–7 proposals stay on **host render worker**; IR impact is cache-key/time-range metadata, not shared GPU across bwrap.  
- **For Synthesis:** Prefer architecture: keep melt→ffmpeg **final**; add **chunked preview** + **source proxies** + Remotion dirty-only; defer live MLT consumer until Review Studio product decision.  
- **Blocker for numbers:** Phase 1 measurements still required before priority among Remotion vs melt vs encode.
