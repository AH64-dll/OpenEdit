# Sandbox & IR Integration Constraints — Render Optimization (2026-08-02)

> Agent 4 deliverable for Phase 6 synthesis. Investigation only — **no product code changed**.  
> Grounded in: `2026-08-02-render-ground-truth.md`, master plan Hard Constraints, Graphify + code for sandbox/IR/render launch.

## 1. Boundary map (what runs where)

| Surface | Process / isolation | IPC / I/O | GPU today |
|---|---|---|---|
| Free-form IR (`run_script` / `FreeFormCodeOp`) | `run_free_form` → `BwrapBackend` → Rust `open-edit-sandbox` (bwrap + seccomp + rlimits) | Scratch `ops.jsonl` → host validates → ops appended to edit graph | **None.** No `/dev/dri`, no CUDA bind, no melt/ffmpeg in this path |
| Motion-graphics skill codegen | `bridge.run_render` → `open-edit-render-sandbox` | Output file under workdir; optional `--with-hwaccel` → `/dev/dri` | Optional, **not** main proxy/final |
| Main proxy / final jobs | `RenderJobService._launch` → `sys.executable -m open_edit.cli render` on **host** | JSON stdout; writes under project `.open_edit/` | Host NVENC + optional melt `hwaccel=cuda` (probe + CPU retry) |
| HyperFrames overlay mode | Host `_launch` → `run_trigger_render` | Separate from melt frame-server spine | Host Chromium/HTML path |
| Edit Graph → emission | Host Python: `derive_timeline` → `materialize_remotion_*` → `emit_timeline` → melt→ffmpeg | Files on host project tree | Remotion: no Chromium GPU flags today |

**Invariant:** Free-form sandbox mutates **IR** (ops). Host render worker consumes **derived timeline / MLT / Remotion**. Do not conflate `bridge.run_render` with `RenderJobService._launch`.

```
Agent / MCP edit ──► EditGraphStore
                         │
         FreeFormCodeOp  │  pillar ops / apply_generated_ops
              │          │
              ▼          │
     bwrap + ops.jsonl ──┘
                         │
                         ▼
              derive_timeline (pure)
                         │
                         ▼
         host render_project (CLI / job worker)
              Remotion → emit MLT → melt|ffmpeg → MP4
```

## 2. Policy vs practice — Python pin

| Claim | Evidence |
|---|---|
| **Policy (Hard Constraint)** | “Python 3.11 strict pin” in master plan |
| **Packaging floor** | `requires-python = ">=3.11"` (`pyproject.toml`) — not `==3.11` |
| **Typecheck pin** | mypy `python_version = "3.11"` |
| **Sandbox “pin”** | `PINNED_PYTHON_BIN = sys.executable` + `EXPECTED_PY_VERSION` from **runtime**, not a fixed 3.11 binary |
| **This host practice** | Runtime **3.14.5** (Phase 0 + reconfirmed) |

**Agent 5 rule:** Treat **3.11 as the supported language/API floor and CI/mypy target**. Flag any proposal that *requires* 3.12+ / 3.14-only APIs, or that assumes the sandbox always runs a dedicated 3.11 interpreter, as **policy vs practice drift** — must say “breaks / softens Python 3.11 pin” or “needs explicit runtime matrix,” not “already pinned to 3.11 only.”

## 3. Hard Constraints (authoritative for Phase 6)

Every Phase 6 recommendation must either **fit** or say **“requires breaking X”** with justification:

1. **Python 3.11 policy pin** (floor + mypy; see §2).
2. **Free-form IR** stays in bwrap/seccomp; **IPC across that boundary is file-based `ops.jsonl`** (validated incrementally against Edit Graph, then committed). No shared memory, sockets, or shared GPU contexts **across the free-form sandbox boundary** unless explicitly broken.
3. **Main render workers may use host GPU** (already true for proxy/final). GPU proposals must label: **sandbox / render worker / both**.
4. **IR is Edit Graph → Python emission** (`derive_timeline` / `emit_timeline` / `build_render_plan`). New evaluation layers must name which of these change.
5. **Compositing stack** remains MLT + ffmpeg frame-server + Remotion + HyperFrames unless Phase 6 explicitly replaces a layer.
6. **Disk budget** — eviction/size caps required for any new cache.
7. **Do not regress** `f=rawvideo` pipe contract without a migration plan.

---

## 4. Preview / export ideas — safe on host vs requires breaking sandbox

### 4.1 Allowed on host render worker (does **not** break free-form sandbox)

These keep IR mutations in `ops.jsonl` / Edit Graph and put heavy compute in host CLI / `RenderJobService` (same class as today’s proxy/final):

| Idea | Why host-safe |
|---|---|
| Faster full-timeline **proxy/final** encode (tiers, NVENC, melt hwaccel, Remotion reuse) | Already host CLI path |
| **Chunked timeline preview cache** (background bake of time ranges → files under project cache) | New job mode / worker tasks; Review Studio plays files or ranges — still host I/O |
| **Serve pre-baked preview chunks** to HTML5 `<video>` / MSE | Serve layer reads host files; no bwrap |
| **Per-asset source proxies** (encode low-res stand-ins into CAS; resolve at plan time) | Host ingest/encode; `resolve_asset_paths` chooses path |
| **Dirty Remotion-only rematerialize** | Host `materialize_remotion_compositions` + composition cache keys |
| Async / skip QC for proxy | Host `RenderJobService._attach_qc` policy |
| Disk eviction for Remotion `out/` + `render_cache` | Host storage policy |
| Interactive scrub that **consumes host-produced cache** (seek within chunks / playlist) | UI + serve; consumer is file-backed |

### 4.2 Allowed on host but **product/architecture** change (sandbox OK; still must be explicit)

| Idea | Note |
|---|---|
| **Interactive MLT consumer** (SDL/OpenGL/live melt in Review Studio) | Not present today (Phase 0: MP4 playback only). Can stay **outside** free-form sandbox if implemented as a **host preview daemon** attached to serve. Does **not** require breaking `ops.jsonl`. Does require new surface + IR/emission contracts (§5). |
| Range-limited MLT emit for chunk jobs | Emission change on host; sandbox untouched |
| Separate audio preview path from video cache | Host player/worker design |

### 4.3 Requires **explicit break** of Hard Constraints

| Idea | What it breaks |
|---|---|
| Run melt/ffmpeg/Remotion **inside** free-form `run_free_form` for “faster preview” | Sandbox purpose (IR-only); no GPU in free-form path; timeout/mem caps (≤300s / 4 GiB) |
| Shared CUDA / Vulkan / GL context or dmabuf **between agent free-form and host melt** | File-only IPC across bwrap; isolation model |
| Replace `ops.jsonl` with sockets / shm / GPU buffers for IR ops | Hard Constraint #2 |
| Bind `/dev/dri` / nvidia into **free-form** bwrap by default | Free-form isolation; conflates with optional `run_render --with-hwaccel` only |
| Move **main** proxy/final into render-sandbox bwrap **and** assume host-class GPU zero-copy | Conflates motion-graphics sandbox with job worker; GPU-across-boundary |
| Agent scripts write MLT/XML or drive melt via sandbox for Review Studio scrub | Emission must stay host-owned; free-form emits **ops**, not live consumers |
| Zero-copy MLT↔ffmpeg that **depends on** sandbox sharing GPU with worker | Worker may already share host GPU with itself; **sandbox↔worker** sharing is the break |

---

## 5. IR / emission changes needed for four Phase-2+ ideas

Today: **Edit Graph ops** → `derive_timeline` (pure) → Remotion materialize (host) → `build_render_plan` / `resolve_asset_paths` → `emit_timeline` → pipe.  
`Clip.asset_hash` is canonical; `Asset` has **no** proxy fields; Remotion cache is per-composition content key; `force=True` on `render_project` skips **final MP4** `RenderCache` only — Remotion still honors its own cache.

### 5.1 Chunked preview cache

| Layer | Needed changes |
|---|---|
| **IR types** | Usually **no new edit ops**. Add a **sidecar cache schema** (not necessarily in edit_graph): chunk id, `[t0,t1)`, content fingerprint, profile, path, status. Optional: op metadata or derived **dirty intervals** helper (clip/composition time ranges from ops). |
| **derive_timeline** | Unchanged for correctness. Add **invalidation map**: applied/reordered/reverted ops → affected time ranges (and Remotion UIDs). |
| **emit / plan** | `emit_timeline` or a sibling must support **range emit** (or per-chunk XML) + chunk profile. `build_render_plan(mode=…)` must stop being mode-agnostic for preview chunks. |
| **Jobs** | New host job kind(s): bake dirty chunks, mark green/red; concurrency with proxy/final via existing locks/semaphore. |
| **Sandbox / ops.jsonl** | **No change** if edits still produce normal ops. |

### 5.2 Interactive scrub consumer

| Layer | Needed changes |
|---|---|
| **IR types** | Minimal for file-chunk scrub. For **live MLT consumer**: may need preview profile pins, optional “preview ignore” flags — prefer project meta / pinned values over new ops until necessary. |
| **derive_timeline** | Must remain the single derived truth the consumer reads (or a snapshot). Live consumer must not re-interpret free-form code. |
| **emit_timeline** | Live path may keep XML in memory / temp; still **host emission**. Do not use `RawMltXmlOp` as the interactive path (escape hatch, not scrub architecture). |
| **Serve / UI** | Replace or augment `<video src=rendered MP4>` with chunk playlist **or** host preview protocol. |
| **Sandbox** | **No GPU/IPC break** if consumer is host-side. Break only if consumer is driven from inside bwrap. |

### 5.3 Per-asset source proxies

| Layer | Needed changes |
|---|---|
| **IR / Asset** | Extend `Asset` (or sidecar): e.g. `proxy_hash`, `proxy_profile`, generation status. **Clips keep canonical `asset_hash`.** |
| **Ops** | Prefer **no** new timeline ops; generation is host maintenance (ingest hook / background job). Optional explicit `GenerateAssetProxyOp` only if auditability requires it. |
| **resolve_asset_paths** | Mode-aware: preview/proxy-edit → proxy file; final → original. |
| **emit_timeline** | Unchanged shape; different resolved paths. |
| **Sandbox** | Free-form may still reference canonical hashes; must not assume proxy files exist inside RO asset binds unless staged. |

### 5.4 Dirty Remotion-only rematerialize

| Layer | Needed changes |
|---|---|
| **IR** | Dirty set = changed `AddRemotionCompositionOp` fields / entry bundle / props / alpha / duration / profile — already approximated by `composition_cache_key`. May expose `composition_uid` dirty list on graph diff. |
| **materialize** | Skip or cache-hit unchanged comps (already). Add explicit **`force_remotion` / per-UID invalidate** separate from `render_project(force=)` MP4 cache bypass. |
| **Orchestrator cache key** | Full-timeline MP4 key still invalidates on any graph change today — dirty Remotion alone does **not** give incremental timeline encode without chunk/dirty-region work (§5.1). |
| **emit / overlays** | `timeline_plan` overlay list can stay; only rematerialize inputs change. |
| **Sandbox** | Remotion stays on **host worker**. Generating Remotion from free-form still emits ops only. |

---

## 6. Red-flag patterns (Agent 5 must reject or force “breaks X”)

1. **“Shared GPU across bwrap”** — free-form and render worker share CUDA context / GL / dmabuf / nvenc session.
2. **Conflating `run_render(--with-hwaccel)` with main jobs** — optional motion-graphics sandbox ≠ `RenderJobService` host CLI.
3. **“Put preview in the sandbox for safety”** — moves GPU/compositor into the IR isolation domain.
4. **Replacing `ops.jsonl` with live RPC/shm** for IR emission without an explicit Hard Constraint break.
5. **Assuming free-form has `/dev/dri`** — `BwrapBackend` argv has sources RO + project meta only; no device binds.
6. **Zero-copy MLT↔ffmpeg that requires sandbox participation** — host worker GPU is fine; sandbox involvement is not.
7. **Treating `mode=proxy` as source proxies or as interactive scrub** — Phase 0: proxy is full-timeline MP4 encode.
8. **“force rematerialize” via only `render_project(force=True)`** — does not force Remotion cache miss today.
9. **Silent Python 3.14-only dependencies** while claiming the 3.11 pin is intact.
10. **Unbounded chunk/Remotion/proxy caches** without eviction — violates disk Hard Constraint.

---

## 7. Constraints checklist — Agent 5 (Phase 6 synthesis)

For **each** Phase 6 recommendation, Agent 5 must fill:

- [ ] **Runs in:** free-form sandbox / host render worker / serve-UI / both (name both if both).
- [ ] **Touches IPC:** `ops.jsonl` only / host files / new host protocol / **breaks file-IPC** (explain).
- [ ] **GPU claim:** none / host worker only / **sandbox GPU** (must be explicit break) / shared across boundary (must be explicit break).
- [ ] **IR path named:** which of `OperationUnion` / `Asset` / `derive_timeline` / `materialize_*` / `build_render_plan` / `emit_timeline` / `RenderJobService` change.
- [ ] **Product bucket:** interactive preview / proxy review artifact / final export / source proxies (do not merge labels).
- [ ] **Python 3.11:** compatible with floor+mypy 3.11 / requires newer (flag policy break) / runtime-matrix note.
- [ ] **Disk:** eviction + size cap described, or N/A with reason.
- [ ] **Pipe contract:** preserves `f=rawvideo` frame-server semantics, or migration plan.
- [ ] **Does not conflate** `bridge.run_render` with main `_launch` host CLI.
- [ ] If any Hard Constraint is bent: section **“Hard Constraints this proposal breaks”** lists them — empty list only if truly none.

**Phase 6 §14 gate:** “none” is allowed only after this checklist is green for every recommendation.

---

## 8. Summary table — allowed vs requires explicit break

| Proposal pattern | Verdict |
|---|---|
| Host NVENC / melt `hwaccel` / faster proxy·final | **Allowed** (host worker) |
| Chunked preview cache baked by host jobs | **Allowed** (host; IR sidecar + emission ranges) |
| Review Studio scrub over host chunk/MP4 files | **Allowed** (serve/UI) |
| Live MLT interactive consumer on **host** preview daemon | **Allowed** (architecture change; sandbox intact) |
| Per-asset source proxies via CAS + `resolve_asset_paths` | **Allowed** (host; Asset/plan IR) |
| Dirty Remotion rematerialize on host | **Allowed** (host materialize API; not free-form) |
| GPU / melt / Remotion inside free-form bwrap | **Requires explicit break** |
| Shared GPU/shm/sockets across free-form boundary | **Requires explicit break** |
| Replace `ops.jsonl` with non-file IR IPC | **Requires explicit break** |
| Default `/dev/dri` in free-form sandbox | **Requires explicit break** |
| Main jobs moved into bwrap + assumed shared host GPU | **Requires explicit break** |
| 3.12+/3.14-only APIs without matrix/pin note | **Requires explicit break** (policy) |

---

## 9. Code anchors (Phase 0 + this review)

- Free-form: `open_edit/agent/sandbox/bridge.py` (`run_free_form`), `backends.py` (`BwrapBackend`, `PINNED_PYTHON_BIN`), `staging.py` (`ops.jsonl` validate).
- Skill render sandbox (not main jobs): `bridge.run_render` / `--with-hwaccel`.
- Main jobs: `open_edit/kernel/render_jobs.py` `_launch` → `python -m open_edit.cli render`.
- Emission spine: `ir/derive.py` → `render/materialize.py` → `render/timeline_plan.py` → `render/emitter.py` → orchestrator pipe.
- IR models: `open_edit/ir/types.py` (`Asset`, `Clip`, Remotion ops; no proxy/chunk types today).
