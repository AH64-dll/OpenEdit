# Changelog

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
