# Open Edit — Compositing / Remotion / HyperFrames (Agent 2)

> Investigation only. No product code changed. Claims cite file:line. Phase 1 must measure before prioritizing Phase 5 ideas.
> Depends on: `docs/superpowers/specs/2026-08-02-render-ground-truth.md`, master plan Phase 0/5.
> Graph orientation: `materialize_remotion_compositions` → `render_composition` / `composition_cache_key` → `build_render_plan` → `timeline_for_melt` + `OverlayClip` → `build_pipe_commands` / `overlay_filter_chain`. HyperFrames: `render_jobs._launch(mode=overlay)` → `kernel/render_overlay.run_trigger_render` → `html_overlay.render_composited`.

---

## 1. Remotion critical path

Ordered steps on every `proxy` / `final` (`render_project`):

| Step | What happens | Evidence |
|---|---|---|
| 1 | Orchestrator always calls materialize **before** RenderCache lookup | `orchestrator.py:135–156` then cache at `217–225` |
| 2 | Per composition: validate entry → source bundle → stage `public/` assets → cache key | `materialize.py:64–87`; `safety.py:35–51,100–162,186–245` |
| 3a **Hit** | `RenderCache.get` under remotion `out/cache` → re-`AssetStore.ingest` → set `asset_hash` → inject `Clip` | `materialize.py:96–105,134` |
| 3b **Miss** | `render_composition` (Node bridge → Remotion Chromium) → ingest → `cache.put` → inject | `materialize.py:106–132`; `renderer.py:157–299,359–382`; `remotion_bridge.mjs` |
| 4 | `build_render_plan`: Remotion → `OverlayClip` list; melt timeline = base v1 only | `timeline_plan.py:20–41,73–149` |
| 5 | Emit MLT **without** Remotion/upper tracks; ffmpeg burns overlays | `orchestrator.py:227–243`; `pipe_builder.py:99–171` |
| 6 | Optional blur-under prepass on base, then sequential `overlay=` windows | `pipe_builder.py:51–96` |

Profile sizing for Remotion itself (independent of melt profile name):

- Proxy materialize: **640×360 @ 30fps** (`renderer.py:129–139`)
- Final materialize: **1920×1080 @ 30fps** (`renderer.py:140–147`)
- Alpha codec: `resolve_alpha_mode` → VP8 if probe proves alpha, else **ProRes 4444** (`renderer.py:42–115,191–216`)

MLT emit does **not** composite Remotion. `timeline_for_melt` strips Remotion clip IDs and keeps only the first video track (`timeline_plan.py:128–149`). Overlays exist solely as ffmpeg `-i` inputs + `filter_complex`.

---

## 2. Cache invalidation — hit vs miss

### Per-composition Remotion cache

- **Location:** `<project>/.open_edit/remotion/out/cache/` via `RenderCache` (`materialize.py:29–36`).
- **Key:** `materialize:<composition_id>:<sha256>` (`materialize.py:35–36,95`).
- **Hash inputs** (`safety.py:219–245`): composition source bundle (tsx + Root registration snippet + public-asset staging version + referenced file SHA256s), `composition_id`, `props`, full `profile.model_dump()`, `alpha`, `duration_sec`, `REMOTION_VERSION`, `ALPHA_POLICY_VERSION`, and again `referenced_files` from props.

**Miss when any of those change**, including:

- TSX / Root registration text for that `composition_id`
- Prop values or bytes of referenced images (`file://` / `staticFile`)
- Proxy↔final profile flip (640×360 vs 1920×1080, vcodec)
- `alpha` flag or alpha policy / Remotion version constants
- `duration_sec`

**Hit:** file exists under key+ext (`.mov` / `.webm` / `.mp4` per alpha codec — `materialize.py:91–96`) and optional metadata `source_hash` matches (`cache.py:83–98`). Then **re-ingest** only — no Chromium.

**Not invalidated by:** timeline position alone (position is not in the key; only duration is). Moving a card without changing duration/props/source → Remotion hit; full MP4 RenderCache still misses if graph hash changes.

### Final MP4 RenderCache vs Remotion cache

- Final deliverable key = graph hash + profile fingerprint + Remotion content fingerprint + source-repair policy (`orchestrator.py:191–216`).
- `force=True` **only** bypasses that final MP4 cache (`orchestrator.py:217–225`). Materialize still runs and **still honors** Remotion `out/cache`. There is **no rematerialize-force flag**.
- Job launcher does not pass `--force` (`render_jobs.py:435–447`).

### Eviction

- Remotion `out/cache` / `out/{proxy,final}`: **no size cap or eviction** in render code (only soft TTL on *final* MP4 freshness via `OPEN_EDIT_RENDER_CACHE_TTL_SEC`, default 24h — `cache.py:20–21,150–159`). Disk pressure is operational (manual cleanup), not policy.

---

## 3. Concrete cost drivers (code evidence)

| Driver | Why it costs | Evidence |
|---|---|---|
| **Serial per-comp Chromium** | One Remotion CLI process per composition in a Python `for` loop; N overlays ⇒ N headless renders on miss | `materialize.py:64–118`; concurrency is **intra**-comp frame workers only (`renderer.py:218–221,323–334`) — no `--gl` / GPU Chromium flags |
| **ProRes 4444 size** | When alpha probe fails (common on this stack per product memory), alpha → `prores` + `yuva444p10le` + `.mov` | `renderer.py:97–115,195–216`; `materialize.py:91–92` |
| **Materialize before MP4 cache** | Even on full deliverable cache hit, Remotion materialize + re-ingest already ran | `orchestrator.py:135–156` then `217–225` |
| **Cache hit still re-ingests** | Hit path copies/hashes into CAS again | `materialize.py:97–105` |
| **N overlay `-i` inputs** | Every Remotion/upper-track clip is a separate ffmpeg input for the **whole** encode; short cards still open ProRes/WebM demuxers for the filter graph | `pipe_builder.py:141–150` |
| **Always `scale=W:H` + often `format=rgba`** | Per overlay, even if Remotion already matched profile size; Remotion overlays default `OverlayClip.alpha=True` because plan does **not** pass `composition.alpha` | `pipe_builder.py:79–89`; `timeline_plan.py:83–89` vs default `OverlayClip.alpha=True` at `pipe_builder.py:26` |
| **blur_under prepass** | Extra `split` + `boxblur=20:10` + enable-window overlay on base for all blur windows | `pipe_builder.py:59–73`; props via `blur_under` (`timeline_plan.py:88`) |
| **`force` does not rematerialize** | Debugging / “force rebuild overlays” still serves Remotion cache | `orchestrator.py:217–225` + `materialize.py:96–98` |
| **Proxy vs final Remotion duplication** | Separate profiles ⇒ separate cache keys; a composition paid twice across modes | `renderer.py:129–147` inside key at `safety.py:237` |

### Historical double-burn (status: fixed)

Remotion was previously at risk of melt multitrack **and** ffmpeg overlay. Current code:

- Strips Remotion from melt (`timeline_plan.py:128–149`; test `test_remotion_proxy_golden.py:142–185`)
- Skips `video_graphics` and Remotion clip IDs in `_video_track_overlay_clips` (`timeline_plan.py:97–125`)

So melt+ffmpeg **double-input of the same Remotion clip is not present**. Remaining cost is **N distinct overlay inputs**, not duplicate burn of one asset.

---

## 4. Remaining correctness risks

| Risk | Detail | Evidence |
|---|---|---|
| **Alpha plan vs composition** | `_remotion_overlay_clips` never sets `alpha=composition.alpha`; defaults True. Opaque Remotion (`alpha=False` → H.264) still gets `format=rgba` in the pipe | `timeline_plan.py:83–89`; `pipe_builder.py:26,79–84` |
| **Alpha codec host dependence** | `auto` → VP8 only if probe proves transparency; else ProRes. Wrong probe ⇒ opaque cards or huge intermediates | `renderer.py:42–108` |
| **filter_complex scale** | Forced fullscreen scale of every overlay; aspect/letterboxing is Remotion’s job, but scale+rgba on ProRes is a decode/convert tax and a footgun if sizes diverge | `pipe_builder.py:79–89` |
| **Overlay input index** | Correct today: inputs `[0]=rawvideo, [1]=audio, [2+]=overlays` via `first_overlay_input=2`. Regression risk if audio mapping changes | `pipe_builder.py:53,139–146,79` |
| **blur_under timing** | Enable windows use escaped commas in blur prepass vs unescaped in overlay enable; covered by unit/ffmpeg tests but fragile to hand-edits | `pipe_builder.py:66–72,90–94`; `tests/test_render/test_pipe_builder.py:36–67,70+` |
| **HyperFrames `[outv]` map** | `composite_with_background` maps `-map [outv]` but filter has no `[outv]` label — overlay-mode correctness bug if that path is used | `html_overlay.py:453–462` |

Not reopened as open product bugs for proxy/final Remotion alpha (probe+ProRes fallback + blur_under verified in prior timeline-test work). Cost and plan `alpha` wiring remain.

---

## 5. Phase 5 optimization ideas (investigation-backed)

Each idea states what **Phase 1** must confirm. No implementation.

1. **Dirty-only rematerialize + skip materialize on deliverable cache hit**  
   Today materialize always runs first.  
   *Measure:* wall clock of `diagnostics.stages.remotion_materialize` on cache-hit re-proxy with unchanged comps vs miss; fraction of time that is re-ingest only.

2. **Proxy alpha codec cheaper than ProRes when probe allows (or proxy-specific alpha policy)**  
   Proxy already uses 640×360; ProRes still dominates disk/decode.  
   *Measure:* bytes and materialize seconds for same FocusPopup under `OPEN_EDIT_ALPHA_MODE=vp8` vs `prores` on fixture B/C; ffmpeg overlay stage time.

3. **Parallel Remotion materialize (process pool) with capped concurrency**  
   Loop is serial; intra-comp `--concurrency` does not help across comps.  
   *Measure:* sum of per-comp Remotion times vs end-to-end materialize (idle gaps); CPU during materialize on fixture C (≥20 overlays).

4. **Reduce ffmpeg overlay input tax (concat short overlays / segmented burn / trim demux)**  
   N ProRes `-i` for full timeline encode.  
   *Measure:* ffmpeg stage time and RSS vs overlay count on A/B/C; time with overlays replaced by null/`color` stubs of same count.

5. **Pass `composition.alpha` into `OverlayClip`; skip `format=rgba` when false**  
   *Measure:* whether any production comps use `alpha=False`; if yes, overlay-stage CPU with/without rgba on those clips.

6. **Remotion cache eviction + shared proxy/final when resolution matches intent**  
   *Measure:* `du` of `remotion/out/{cache,proxy,final}` vs CAS after heavy C runs; hit rate after editing one of N comps.

7. **Optional rematerialize force / bust key** separate from MP4 `force`  
   *Measure:* how often operators use `--force` expecting overlay rebuild (support/ops); currently force never busts Remotion cache.

8. **Defer blur_under to Remotion or a single pre-blurbed plate** when many overlapping windows  
   *Measure:* ffmpeg filter graph time with blur_under on/off for C-like timelines.

---

## 6. HyperFrames relative to proxy/final

| Question | Answer | Evidence |
|---|---|---|
| On hot path for typical proxy/final? | **No.** Job mode `proxy`/`final` → `python -m open_edit.cli render` → melt→ffmpeg spine. | `render_jobs.py:418–435` |
| When does HyperFrames run? | Only `mode=overlay` **and** timeline has `HtmlOverlay` entries | `render_jobs.py:420–433`; `render_overlay.py:93–107,271–275` |
| Typical FocusPopup / Remotion workflow? | Uses `AddRemotionCompositionOp` / Remotion materialize, **not** HyperFrames | IR `RemotionComposition` vs `HtmlOverlay` (`types.py:42–91`); MCP playbook: Remotion for titles, `overlay` mode = HyperFrames HTML |
| Relative importance | **Low** for proxy/final wall clock. Remotion materialize + ffmpeg overlay burn dominate compositing cost on Remotion-heavy projects. HyperFrames matters only if product re-emphasizes `mode=overlay` HTML templates. | Ground truth § overlay branch; plan Agent 2 note |

HyperFrames still has its own Chromium (hyperframes CLI → `.mov`) + ffmpeg composite (`html_overlay.py:378–475`) and a likely `[outv]` mapping bug — profile separately if overlay mode is claimed slow; do not conflate with proxy/final Remotion cost.

---

## 7. Artifact note

`/home/ah64/OpenEditProjects/timeline-test` currently has **no** `.open_edit/remotion/out` tree in this environment (project dir holds staged images/thumbs only). Remotion cache size claims rely on code + prior ops memory (~hundreds of MiB `out/cache`+proxy cleaned 2026-08-02), not a live peek.

---

## Top findings (summary)

1. Remotion is on the critical path **before** MP4 cache; Chromium runs **serially per composition** on miss; hit still re-ingests.
2. Alpha→ProRes 4444 `.mov` is the dominant Remotion disk/decode tax when VP8 alpha probe fails.
3. Overlays are ffmpeg-only (melt stripped); cost is **N overlay inputs** + scale/rgba/blur_under — historical melt+ffmpeg double-burn is fixed.
4. `force` does not rematerialize Remotion; no Remotion cache eviction policy.
5. HyperFrames `mode=overlay` is **off** the typical proxy/final hot path; Remotion dwarfs it for current workflows.
