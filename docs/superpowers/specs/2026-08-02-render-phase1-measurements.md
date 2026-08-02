# Open Edit Render Phase 1 — Measurements (2026-08-02)

> Instrumented investigation only. No product architecture proposals. No `open_edit/` code changes.
> Ground truth: `docs/superpowers/specs/2026-08-02-render-ground-truth.md`.
> Raw JSON: `docs/superpowers/specs/phase1-raw/*.json`.
> Harness: `docs/superpowers/scripts/phase1_{setup_fixtures,run_bench}.py`.

## Host / environment

| Item | Value |
|---|---|
| Date | 2026-08-02 (local) |
| Disk before bench | `df /` ≈ **87–88%** used, **~14–16 GiB** free |
| Disk after prune | **~88%**, **~15 GiB** free |
| GPU | NVIDIA GeForce RTX 4050 Laptop (6 GiB), driver 610.43.02 |
| Encoder backend (measured) | `gpu` (`fast_proxy\|q=fast\|enc=gpu`, `1080p30\|q=standard\|enc=gpu`) |
| Python | 3.14.5 (venv `.venv`) |
| melt | 7.40.0 |
| ffmpeg | n8.1.1 |
| Chrome (Remotion) | Google Chrome 150.0.7871.114 via `--browser-executable` |
| Alpha capability probe | **`False`** → Remotion alpha path = **ProRes 4444** (`.mov`) |

**timeline-test note:** `/home/ah64/OpenEditProjects/timeline-test/.open_edit` was **missing** at Phase 1 start (source `untitled_clean_1.mp4` still present). Fixtures were built under disposable `/home/ah64/OpenEditProjects/render-bench/` from trimmed CAS media — **timeline-test edits were not modified**.

## Fixtures

| Fixture | Path | Media | Timeline | Remotion |
|---|---|---|---|---|
| **A** | `…/render-bench/fixture-a` | `media/clip60.mp4` (1080p H.264 trim) | ~60.03 s, V1+A1 | **0** |
| **B** | `…/render-bench/fixture-b` | same 60 s | ~60 s | **3× FocusPopup**, `alpha=true`, 3 s each @ 5/20/40 s |
| **C** | `…/render-bench/fixture-c` | `media/clip180.mp4` | ~180 s | **12× TitleCard**, opaque, 3 s each @ 8+13 i s |

Media creation:

```bash
ffmpeg -y -ss 0 -t 60  -i …/timeline-test/untitled_clean_1.mp4 \
  -c:v libx264 -preset veryfast -crf 23 -c:a aac -b:a 128k -movflags +faststart \
  /home/ah64/OpenEditProjects/render-bench/media/clip60.mp4
# likewise -t 180 → clip180.mp4
```

Fixture graph setup: `docs/superpowers/scripts/phase1_setup_fixtures.py` (`open_edit.cli init` + `AddClipOp` / `AddRemotionCompositionOp`).

## Measurement method

1. Harness calls `render_project()` then `run_qc_gate()` with monkeypatched timers around `derive_or_load_timeline`, Remotion `render_composition`, and Remotion materialize `RenderCache.get`.
2. Stage times for Remotion / melt / ffmpeg / repair come from orchestrator `diagnostics` where available.
3. **`melt` diagnostic ≈ 0 s always:** `melt_runner.run_pipe` records `melt_elapsed_sec` as the **residual wait after ffmpeg exits** on the concurrent melt→rawvideo→ffmpeg pipe (`melt_runner.py` ~159–166). **Pipe wall clock ≈ `ffmpeg` stage.**
4. Remotion Chromium: stock Remotion chrome-headless-shell download **failed** on this host. Measurements used Phase-1-only wrapper:
   - `OPEN_EDIT_REMOTION_BIN=docs/superpowers/scripts/remotion_with_chrome.sh`
   - `OPEN_EDIT_CHROME_EXECUTABLE=/usr/bin/google-chrome-stable`
5. Cold = `--force` (bypass final MP4 `RenderCache`). Warm = identical second run (no force).
6. First process invoke also pays a one-shot `_gpu_decode_available()` melt probe (~few seconds) outside stage sums — visible as wall−accounted residual on A cold.

Example command:

```bash
export OPEN_EDIT_REMOTION_BIN=/home/ah64/apps/mlt-pipeline/docs/superpowers/scripts/remotion_with_chrome.sh
export OPEN_EDIT_CHROME_EXECUTABLE=/usr/bin/google-chrome-stable
/home/ah64/apps/mlt-pipeline/.venv/bin/python \
  docs/superpowers/scripts/phase1_run_bench.py C --mode proxy --force \
  --label C_proxy_cold --out docs/superpowers/specs/phase1-raw/C_proxy_cold.json
```

## End-to-end wall clock (seconds)

| Fixture | Mode | Cold wall | Warm wall | Warm `RenderCache` hit? |
|---|---|---:|---:|---|
| A | proxy | **22.825** | **5.006** | yes |
| A | final | **56.939** | **8.635** | yes |
| B | proxy | **46.133** | **5.732** | yes |
| B | final | **97.655** | **9.582** | yes |
| C | proxy | **157.172** | **15.426** | yes |
| C | final | **286.320** | **23.912** | yes |

## Stage breakdown — cold runs (seconds)

| Run | Derive | Remotion mat. | Pipe≈ffmpeg | Audio melt | Source-repair | QC | Wall |
|---|---:|---:|---:|---:|---:|---:|---:|
| A proxy | 0.004 | 0.0 | **13.639** | 0.707 | 0.676 | 0.922 | 22.825 |
| A final | 0.0 | 0.0 | **41.603** | 0.683 | 3.703 | 4.101 | 56.939 |
| B proxy | 0.0 | **24.701** | 13.891 | 0.677 | 0.676 | 0.905 | 46.133 |
| B final | 0.0 | **36.145** | **45.906** | 0.629 | 4.536 | 5.073 | 97.655 |
| C proxy | 0.005 | **93.720** | 42.901 | 1.456 | 1.611 | 1.899 | 157.172 |
| C final | 0.001 | **111.453** | **133.277** | 1.405 | **13.156** | **13.032** | 286.320 |

`melt` diagnostic column omitted (always ~0; see method). Repair returned `ok=true`, `changed=false` on all successful cold runs (elapsed still paid for analysis pass).

## Remotion detail (cold)

| Run | # comps | Cache hits | Render-miss wall sum | Per-comp min/mean/max (s) | Approx % of wall |
|---|---:|---:|---:|---|---:|
| B proxy | 3 FocusPopup α | 0 | **24.46** | 7.67 / 8.15 / 8.97 | **53%** (24.7/46.1) |
| B final | 3 FocusPopup α | 0 | **35.88** | 11.13 / 11.96 / 12.41 | **37%** (36.1/97.7) |
| C proxy | 12 TitleCard | 0 | **93.20** | 7.26 / 7.77 / 8.77 | **60%** (93.7/157) |
| C final | 12 TitleCard | 0 | **110.93** | 8.47 / 9.24 / 10.88 | **39%** (111/286) |

Alpha overlays (B) wrote ~7 MiB ProRes `.mov` each at proxy size; opaque TitleCards (C) were far smaller on disk (`remotion/out` ~3.6 MiB proxy / ~7.8 MiB final vs B ~104 MiB remotion out after both modes).

## Cache behavior — warm (second identical run)

| Run | RenderCache hit | Remotion composition cache hits | Remotion mat. (s) | QC (s) | Wall (s) |
|---|---|---:|---:|---:|---:|
| A proxy | yes | 0 (no comps) | 0.0 | 0.928 | 5.006 |
| A final | yes | 0 | 0.0 | 4.432 | 8.635 |
| B proxy | yes | **3** | 0.206 | 1.060 | 5.732 |
| B final | yes | **3** | 0.222 | 4.698 | 9.582 |
| C proxy | yes | **12** | 0.456 | 1.887 | 15.426 |
| C final | yes | **12** | 0.495 | 10.791 | 23.912 |

**Observations (numbers only):**

- Remotion materialize still runs before the MP4 cache check (Phase 0); warm Remotion cost drops to **~0.2–0.5 s** via composition cache hits.
- Warm wall is dominated by **QC** (and leftover fixed overhead), not encode: e.g. C final warm **10.8 s QC of 23.9 s wall**.
- Identical graph+profile → full MP4 `RenderCache` hit (`cache_hit_render=true`, melt/ffmpeg/repair skipped).

## Disk usage (during / after)

| Checkpoint | `df /` used | Free |
|---|---|---|
| Start of Phase 1 | ~87% | ~16 GiB |
| Peak during C final | ~89% | ~13.4 GiB |
| After pruning remotion `out/*`, render_cache, large MP4s | ~88% | ~15 GiB |

Peak project footprints (from cold JSON `project_bytes`, before prune):

| Fixture after its cold finals | project_total | remotion_out | renders | remotion `node_modules` |
|---|---:|---:|---:|---:|
| B (proxy+final) | ~630 MiB | ~103 MiB | ~161 MiB | ~212 MiB |
| C (proxy+final) | ~998 MiB | ~7.4 MiB | ~482 MiB | ~212 MiB |

Bench root after prune ≈ **739 MiB** (mostly media + assets + one remotion `node_modules` on B). Large deliverable MP4s pruned after numbers captured; raw JSON retained under `phase1-raw/`.

## Bottlenecks (named only with citations)

1. **Remotion materialize on overlay-heavy proxy** — Fixture **C proxy cold**: Remotion **93.720 s** of **157.172 s** wall (**~60%**); 12 sequential render-misses summing **93.20 s** (~7.8 s/comp). Fixture **B proxy cold**: Remotion **24.701 s** of **46.133 s** (**~53%**).
2. **Concurrent melt→ffmpeg pipe on long / final encodes** — Fixture **C final cold**: pipe≈ffmpeg **133.277 s** vs Remotion **111.453 s** of **286.320 s** wall. Fixture **A final cold** (0 Remotion): pipe **41.603 s** of **56.939 s**.
3. **Per-composition Remotion cost is roughly additive** — B proxy 3× ~8 s; C proxy 12× ~7.8 s mean; no parallel composition materialize observed.
4. **Alpha → ProRes on this host** — `probe_alpha_capability()=False` → ~7 MiB/3 s overlay at proxy; B remotion out after both modes **~104 MiB** vs C’s opaque **~8 MiB**.
5. **Source-repair + QC scale with final length** — C final cold: repair **13.156 s** + QC **13.032 s** even with `changed=false`. Warm cache hits still pay QC (C final warm QC **10.791 s**).
6. **Warm path already skips encode** — RenderCache hit → wall mostly QC/overhead (A/B proxy warm **~5–6 s**); Remotion composition cache prevents rematerialize cost.

## Commands run (index)

```text
# media
ffmpeg … → render-bench/media/clip{60,180}.mp4

# fixtures
.venv/bin/python docs/superpowers/scripts/phase1_setup_fixtures.py

# each measurement (OPEN_EDIT_REMOTION_BIN set for B/C)
.venv/bin/python docs/superpowers/scripts/phase1_run_bench.py {A|B|C} \
  --mode {proxy|final} [--force] --label … --out docs/superpowers/specs/phase1-raw/….json

# remotion browser workaround validation
./node_modules/.bin/remotion render … --browser-executable=/usr/bin/google-chrome-stable
```

Labels produced: `A_proxy_{cold,warm}`, `A_final_{cold,warm}`, `B_proxy_{cold,warm}`, `B_final_{cold,warm}`, `C_proxy_{cold,warm}`, `C_final_{cold,warm}` (+ earlier failed B attempts without Chrome bridge retained historically only in terminal logs; successful JSON overwritten).

## Explicit non-goals / caveats

- No architecture proposal in this document (Phase 2+).
- Fixture C is **180 s / 12 overlays**, not a restored timeline-test graph (`.open_edit` absent).
- Remotion measured with **system Chrome** via Phase-1 wrapper, not default headless-shell download.
- `melt` stage field is **not** melt CPU time; use **ffmpeg** stage as pipe wall.
