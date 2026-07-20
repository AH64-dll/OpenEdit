# Changelog

## v1.2.0 (2026-07-20) — CI infrastructure

Sets up GitHub Actions CI to actually run the bwrap-dependent tests that v1.1 added but ignored. No user-facing changes; pure infrastructure.

### Added

- **`.github/workflows/ci.yml`** — GitHub Actions workflow with 3 jobs:
  - `python-unit` — 308 Python unit tests on Python 3.11, 3.12, 3.14 (~2 min)
  - `rust-build` — `cargo build` + `cargo test` on the Rust sandbox (~1 min)
  - `bwrap-tests` — un-ignores the 5 Rust integration tests and 5 Python e2e tests from v1.1; uses the `bin/setup_render_cgroup.sh` script with sudo to set up cgroup v2 (~5-10 min)
- Runs on every push to main, every PR to main, every tag of the form `v*`, and manual dispatch
- Concurrency: cancels in-progress runs on PRs; never cancels on main

### Notes

- The 5 Rust integration tests and 5 Python e2e tests are un-ignored in CI but stay ignored/skipped locally (where bwrap + cgroup v2 may not be available). This is the v1.2 follow-up filed at `.superpowers/sdd/v1.2-followup.md`, now resolved.
- The `bwrap-tests` job is the only one that requires passwordless sudo. GitHub-hosted `ubuntu-latest` runners have this.
- For local testing of the workflow, install [`act`](https://github.com/nektos/act) and run `act -j python-unit` (the bwrap job will not work locally without bwrap + cgroup v2 setup).

## v1.1.0 (2026-07-20) — Polish release

Resolves all 7 review-flagged polish items from the final whole-branch review of Phase 4 + 4.5. No new features; pure quality work + operator tooling.

### Fixed

- **Conftest I-1** (`open_edit/tests/conftest.py`): `tmp_project_with_assets` fixture now seeds the on-disk edit graph with an `AddClipOp` referencing a real `AssetStore`-ingested asset, instead of using an in-memory-only `Project.assets` dict. Unblocks 4 of 5 e2e tests in `test_free_form_e2e.py` in bwrap-capable environments.
- **Render sandbox cgroup setup** (new `bin/setup_render_cgroup.sh` + `docs/operator-setup.md`): operator-script for creating the cgroup v2 directory that the render sandbox's documented `MemoryMax=4G` + `CPUQuota=300%` limits depend on. Idempotent, shellcheck-clean, with systemd unit example.
- **5 missing Rust integration tests** (`open_edit/sandbox/tests/integration.rs`): `e2e_network_blocked`, `e2e_source_ro_blocks_writes`, `e2e_timeout_kills_runaway`, `e2e_parent_id_stamped`, `e2e_python_version_mismatch`. Fills the gap from spec §7.1's 6-test list (only 1 was previously implemented).
- **Stdout pollution in sandbox binary** (`open_edit/sandbox/src/main.rs`): bwrap child stdout is now piped (not inherited), so free-form script `print()` calls no longer corrupt the protocol JSON. Uses `child.wait_with_output()` (concurrent pipe reads) to avoid the pipe-buffer deadlock risk.
- **Hard-cap clamp direct tests** (`open_edit/tests/test_sandbox_bridge.py`): 2 new tests assert that `run_free_form` clamps `timeout` and `mem_mb` to `MAX_FREEFORM_TIMEOUT_SEC` and `MAX_FREEFORM_MEM_MB` before passing to the Rust binary.
- **Cleanup pass**: removed 6 unused imports from `test_sandbox_bridge.py` (M-7); removed dead `--ops-output` CLI flag from Rust + Python wrapper + e2e test (M-6); fixed the placeholder bootstrap in the ignored `e2e_python_runs_and_writes_ops` test (M-5).
- **IR bootstrap safety net** (`open_edit/tests/test_sandbox_bridge.py`): rewrote the C1 regression test to derive the expected op class list from `OperationUnion` via `typing.get_args`, so adding a 25th op class without updating the sandbox's `op_types` list is automatically caught. Pydantic-version-stable.

### Notes

- 5 Rust integration tests are `#[ignore]`-d and require bwrap + cgroup v2 to run. A v1.2 follow-up will set up CI infrastructure (privileged Docker container or self-hosted runner) to un-ignore them.
- 5 Python e2e tests are still skipped without bwrap. The T1 fix unblocks them in bwrap-capable environments.
- The cgroup setup script must be re-run after each reboot, or installed as a systemd unit (documented in `docs/operator-setup.md`).

## v1.0.0 (2026-07-19) — Initial release

Phase 4 (review room) + 4.5 (creation pipeline) complete. See `.superpowers/sdd/progress-phase4.md` for the full task ledger.
