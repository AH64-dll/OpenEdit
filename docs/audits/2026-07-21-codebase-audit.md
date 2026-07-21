# Codebase Audit — 2026-07-21

**Scope:** 83 Python files, 12,573 lines; 5 Rust files, 640 lines; 2 TypeScript files, 568 lines.
**Method:** Ruff (lint) + MyPy (types) on the Python tree; manual review of 8 high-risk files; parallel subagent deep-dives on 4 critical modules (`html_overlay.py`, `pi_bridge.py` + `agent.py`, `sandbox_bridge.py` + `apply.py`, `cli.py` + `projects.py` + `serve_env.py` + `app.py`).
**Baseline:** 616 passed, 5 skipped. No linters, type checkers, pre-commit, or CI checks were in place; `ruff` and `mypy` were installed for this audit.

## Verdict

The v1.6 overlay integration (just shipped) is clean of Critical issues but has **1 Critical pre-existing bug** elsewhere (`parser_notes` → `p_notes` at `cli.py:312`). The full audit found **4 Critical / Important bugs introduced or perpetuated in v1.6 code** plus **dozens of pre-existing issues** in older code.

Tool inventory: nothing was configured. Recommend adding ruff + mypy to pyproject.

## Tool outputs

### Ruff
- 41 errors total: 28 F401 (unused imports), 5 F821 (false positives from `from __future__ import annotations`), 4 E701 (multi-statement lines in `qc/thumbnail.py`), 3 F841 (unused local variables), 1 F541 (f-string without placeholders).
- 31 errors auto-fixable with `ruff check --fix`.

### Mypy
- 135 errors with `--ignore-missing-imports`.
- Most are `TypedDict total=False` "extra key" false positives (the existing code uses `total=False` plus an `extra=` comment, which mypy doesn't recognize).
- 5 are the `callable` type-annotation bug (see V2 below).
- Real findings cluster in `serve/llm.py`, `serve/agent.py`, `agent/sandbox_bridge.py`, `ir/apply.py`.

## v1.6-relevant findings

### V1 — Critical
**`serve/agent.py:288-294` → `serve/pi_bridge.py:296-302`**

The Task 4 fix that added `mode="overlay"` dispatch to `serve/agent.py:_execute_trigger_render` calls `pi_bridge._run_trigger_render`, which calls `asyncio.run(html_overlay.render_composited(...))`. When invoked from the in-process agent loop (a running event loop), this raises `RuntimeError: asyncio.run() cannot be called from a running event loop`. Bug is invisible to pi-extension users (their subprocess is a fresh loop) but breaks the in-process agent path entirely. **No test covers this path.**

**Fix:** Split `render_composited` into a sync helper that detects a running loop and uses `asyncio.run_coroutine_threadsafe` + `concurrent.futures`, or refactor the in-process agent to call `render_composited` directly via `await`.

### V2 — Important
**`serve/html_overlay.py:265, 379, 434, 483-484`**

5 type annotations use `"callable"` (the predicate), not `Callable[[], bool]`. MyPy already flags. Works at runtime because annotations are stringified, but breaks editor tooling and static analysis.

**Fix:** Add `Callable` to the `from typing import Any` import (line 51), then:
- line 265: `should_cancel: Callable[[], bool] | None,`
- line 379: `should_cancel: Callable[[], bool] | None = None,`
- line 434: `should_cancel: Callable[[], bool] | None = None,`
- line 483: `bg_renderer: Callable[[], str | Path],`
- line 484: `should_cancel: Callable[[], bool] | None = None,`

### V3 — Important
**`serve/pi_bridge.py:251`; `serve/agent.py:309`**

ffmpeg stderr/stdout echoed verbatim into the `detail` field of `trigger_render` results — can be megabytes of `frame= … time= … speed= …` noise, blowing up the LLM's context window and leaking any host paths or arguments that appeared in the ffmpeg log.

**Fix:** Truncate to last ~2 KB before including in `detail`:
```python
def _tail(s: str, n: int = 2000) -> str:
    return s if len(s) <= n else "…" + s[-n:]
detail=f"exit {proc.returncode}: {_tail(proc.stderr.strip() or proc.stdout.strip())}"
```

### V4 — Important
**`serve/agent.py:322-327` vs `serve/pi_bridge.py:279-284`**

In-process agent's `trigger_render` returns `{mode, output_path, stdout, stderr}`; pi-bridge returns `{output_path, mode, duration_s, render_id}`. The verification stage (agent.py:403) reads `result.get("render_id", "render_unknown")` — for the in-process path this is always `"render_unknown"`, breaking correlation with the rest of the system. The agent path also lacks `duration_s`.

**Fix:** Add `render_id` (use the same `render_<hex>` generator) and `duration_s` (probe via `_probe_duration` if output exists) to the agent path.

## Pre-existing Critical / Important findings

| # | Sev | File:line | Issue |
|---|---|---|---|
| P1 | **Critical** | `cli.py:312` | `parser_notes.print_help()` — name `parser_notes` does not exist. Actual variable is `p_notes` (line 372). `open_edit notes` (no subcommand) raises `NameError`. **Verified by running it.** |
| P2 | **Important** | `serve/agent.py:174-189` | `_save_cost_state` does a non-atomic read-merge-write. Concurrent agent turns in the same project clobber each other's cost updates. |
| P3 | **Important** | `serve/projects.py:307-314` | `create_project` swallows `init` failures silently. Returns a 201 with a broken project (no `edit_graph.db`) that is invisible to `list_projects`. |
| P4 | **Important** | `serve/projects.py:194-196, 344-345, 355-356` | `except Exception: pass` in `get_project_state` and `_list_assets_from_disk` — corrupt DBs / bad JSON look identical to "no data". |
| P5 | **Important** | `serve/app.py:75-86, 289` | `_RENDER_JOBS` is an unbounded module-level dict; memory leak for long-running server. |
| P6 | **Important** | `serve/pi_bridge.py:140-164` | `_read_mlt_profile` always returns 1920×1080@30 even when the project has a profile. Documented as fallback but always taken — every non-1080p project silently upscales/downscales. |
| P7 | **Important** | `serve/pi_bridge.py:179` | `_should_use_composited` swallows all exceptions in `_load_timeline` and silently falls through to bare-MLT. Real timeline-load bugs become "no overlays" with no log. |
| P8 | **Important** | `agent/sandbox_bridge.py:93-95` | `shutil.which("open-edit-sandbox")` trusts `$PATH`. The only finding that bypasses every defense the Rust binary provides. |
| P9 | **Important** | `agent/sandbox_bridge.py:98-188, 622-636` | `workdir` not validated before host-side staging writes (`code.py`, `_render_code.py`, `bootstrap.py` to a caller-supplied dir). `project_path="/etc"` from a tool call → arbitrary file write on host. |
| P10 | **Important** | `serve/pi_bridge.py:294-295` | `_run_trigger_render` does not validate `mode` before baking into the render spec. |
| P11 | **Important** | `serve/pi_bridge.py:177, 299` | `_load_timeline` called twice on the composited path — wasted work, race window. |
| P12 | **Important** | `serve/pi_bridge.py:240` vs `serve/agent.py:302` | Render timeouts diverge: 1800s (pi) vs 600s (in-process). Same operation behaves differently depending on driver. |
| P13 | **Important** | `serve/pi_bridge.py:312-313` | When `OverlayRenderError` carries no `bg_path`, fallback re-runs the bg (the slow part) instead of returning a failure result. |

## Categories of issues

- **Static analysis (ruff):** 41 errors — see breakdown above.
- **Static analysis (mypy):** 135 errors — see breakdown above.
- **Race conditions:** 2 important (sibling-task cancellation in `render_composited`; sidecar read-merge-write in `_save_cost_state`).
- **Error handling:** 6 minor (bare `except`, swallowed exceptions, info disclosure via `repr`).
- **Resource leaks:** 2 (unbounded `_RENDER_JOBS`, scratch-dir cleanup on success in `run_free_form`).
- **Test gaps:** 4 noted (no integration test for `mode="overlay"` via in-process agent; no test for `parser_notes` path; no test for parent watchdog timeout; no test for scratch dir cleanup on success).

## Pre-existing minor / note findings (selected)

- `cli.py:197` — `cmd_free_form` reads user-supplied `code_file` with no size or content guard; `/dev/urandom` or a 1 GB file would OOM the process.
- `cli.py:23-30` — `_find_existing_project` walks parents to filesystem root with no max depth.
- `serve/projects.py:62` — bare `except Exception` in `_resolve_project_path` swallows typos.
- `serve/projects.py:157-166` — module-scope `asyncio.Lock()` (legal on 3.10+, but ugly).
- `serve/serve_env.py:81-86` — `get_overlay_config` uses `""` as a sentinel for "auto-resolve" but `overlay_tmpdir` uses `None`. Inconsistent.
- `serve/app.py:151-169` — global exception handler is broader than needed and uses `traceback.print_exc()` instead of structured logging.
- `ir/apply.py:184-189, 203-208` — `endswith` transition-id match is overly broad; matches unintended effects if ids collide.
- `ir/apply.py:618-625` — `derive_timeline` parent walk has no cycle protection; tampered DB hangs.
- `ir/apply.py:316-336, 393-439` — `_apply_change_clip_speed` and `_apply_normalize_audio` accept any rate / target_dbfs. No `gt=0` constraint.
- `ir/apply.py:102-103, 113-115, 222-223, 232-233, 241-242, 288-289, 300-301, 317-319, 340-342, 364-366, 371-373, 402-405, 521-524, 566-568` — `apply_operation` silently no-ops on every bad reference; no `ApplyError`, no log.
- `agent/sandbox_bridge.py:156-158` — `repr(e)` in the top-level safety net echoes absolute paths and exception args back to the LLM.
- `agent/sandbox_bridge.py:226-237, 666-668` — child stderr/stdout echoed into result detail (mild info disclosure + prompt-injection surface).
- `agent/sandbox_bridge.py:180-183, 632-636` — staging writes are non-atomic; SIGKILL between `open` and `write` leaves a corrupt scratch dir.
- `agent/sandbox_bridge.py:189-203, 652-661` — `TimeoutExpired` kills the immediate child, not bwrap's descendants; they get reparented to PID 1 and continue.
- `serve/llm.py:526, 531, 536, 557, 589, 598, 605, 696, 727, 744, 749, 758, 773` — TypedDict `StreamEvent` and `AgentEvent` use `total=False` with comment-only `extra=` declarations; mypy doesn't recognize them.
- `serve/agent.py:740, 763-764` — `int(object)` and `float(object)` calls; `object` is not numeric.
- `serve/agent.py:659` — `MAX_AGENT_ITERATIONS = 10` is a local-scope magic number; not tunable from env.
- `serve/agent.py:725-726` — `provider_does_tool_exec` re-resolved every loop iteration; provider doesn't change mid-turn.
- `serve/agent.py:796-798, 860-862, 1020-1021` — `_save_cost_state_async` is fire-and-forget with no lock; races documented above.
- `serve/html_overlay.py:512-560` — sibling async tasks are not cancelled on partial failure; the bg encoder can run for 30 minutes after a stage fails.
- `serve/html_overlay.py:261-326` — watcher thread is `daemon=True` with `timeout=2.0` join; if the join times out the daemon thread continues running until the OS process exits.
- `serve/html_overlay.py:281, 301, 328, 513, 516, 537, 557` — every `should_cancel()` call is unprotected; a faulty predicate could leak the orchestrator.
- `serve/html_overlay.py:332-334` — non-zero exit error truncates stderr to 500 chars; hyperframes lint traces are often longer.
- `serve/html_overlay.py:121` — error message embeds variable name and type but not the overlay id; operator has to grep the timeline.
- `serve/html_overlay.py:407, 413` — `subprocess.Popen` has no `cwd=` arg; relies on hyperframes internally `chdir`-ing to the positional `[DIR]` arg. Defensive `cwd=str(tmp_project_dir.resolve())` would be safer.
- `serve/html_overlay.py:465` — `composite_with_background` reuses `render_spec["hyperframes_timeout_s"]` for ffmpeg; the variable name is misleading.
- `serve/html_overlay.py:566-571` — `finally` block does not delete partial `final.mp4` or `bg.mp4` on failure; if `tmpdir` is a persistent `OPEN_EDIT_OVERLAY_TMPDIR`, files accumulate indefinitely.
- `serve/html_overlay.py:394-398` — `render_overlay_layer` reads `comp_html` and writes it back to the same path; wasted round-trip.
- `serve/pi_bridge.py:130-137` — `_make_should_cancel` is permanently `lambda: False`; renders cannot be cancelled mid-flight.
- `serve/pi_bridge.py:167` — `_should_use_composited` ignores its `render_spec` parameter.
- `serve/pi_bridge.py:236, 298`; `serve/agent.py:298` — `cwd=str(project_path)` uses `str()` where `Path` would be consistent with the rest of the module.
- `serve/pi_bridge.py:254-265` — "last non-empty line is a path" heuristic for the CLI output is fragile.
- `test_serve_agent_visual_verify.py:127` — `monkeypatch.setattr("subprocess.run", ...)` patches the builtin globally; correct as-is but worth noting.
- `test_serve_agent_visual_verify.py` — no test exercises `mode="overlay"` in the in-process agent path; this is why V1 wasn't caught.
- `test_html_overlay.py:565-592, 595-617` — cancellation tests use `time.sleep(0.1)` synchronization; tight race window.
- `test_html_overlay.py:949-962` — `if "hyperframes" in cmd[0]` would miss `cmd[0] == "npx"`; brittle.
- `test_html_overlay.py:929-977` — integration test has no `pytest.timeout(180)`; a hanging real hyperframes call blocks CI for 120 s.
- `test_html_overlay.py:735-777` — `test_render_composited_writes_composition_html_to_compositions_subdir` does not actually verify the HTML was written.
- `test_html_overlay.py:325-333` — symlink-escape test uses `tmp_path / ".." / "outside_target.html"`; fragile if pytest changes `tmp_path` resolution.
- `test_sandbox_bridge.py:870-874` — `op_raw.parent_id = "p1"` reassignment is a no-op; comment misleads.
- `test_sandbox_bridge.py` — no test for parent watchdog timeout, negative `timeout`/`mem_mb`, output-outside-workdir, scratch cleanup on success.

## What this audit does NOT cover

- Race conditions in concurrent code paths beyond those flagged.
- Design-level smells (overuse of `dict[str, Any]`, missing type contracts on internal APIs).
- The Rust sandbox binary (`sandbox/src/*.rs`) — only the Python bridge is audited.
- The TypeScript pi extension (only the Python side that it talks to is audited).
- MyPy and ruff were run with permissive flags (`--ignore-missing-imports` for mypy, default rule selection for ruff). Stricter runs would find more.
- Performance profiling.

## Recommended order of work

1. **P1** — `parser_notes` → `p_notes`. One-line fix, ship-blocker.
2. **V1** — `asyncio.run()` collision. Breaks the in-process agent's `mode="overlay"` path; needs a test that exercises the in-process path.
3. **P9 + P8** — sandbox bridge `workdir` validation + binary path pinning. Security-relevant; if `open-edit-sandbox` is on a malicious PATH or the LLM can pass `workdir=/etc`, the agent escapes.
4. **V2, V3, V4** — v1.6-introduced issues. Quick wins.
5. **P2, P3, P4, P5** — agent/projects resource and error-handling cleanup.
6. **P6, P7, P10, P11, P12, P13** — pi_bridge correctness cleanup. Most are in the same file, can be batched.
7. **The 28 ruff --fix unused imports + 1 f-string** — mechanical.
8. **Add a `ruff` config to `pyproject.toml` and a `noxfile.py`** so this doesn't have to be done by hand next time.
