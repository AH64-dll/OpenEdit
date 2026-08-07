# Task 7 Brief

### Task 7: Document policy, operator controls, and M0 terminology

**Files:**
- Modify: `.env.example`
- Modify: `skills/qc-standards.md`
- Modify: `open_edit/harness_skills/qc-standards.md`
- Modify: `docs/MCP.md`
- Test: `tests/test_mcp_server.py`
- Test: `tests/test_serve_projects.py`

**Interfaces:**

- Consumes: the final `AssetInfo` proxy fields, `QCReport.policy/complete`,
  cache diagnostics, and the explicit emission-profile names.
- Produces operator and agent documentation that uses three distinct terms:
  `mode=proxy` review artifact, per-asset source proxy, and future timeline
  preview chunks.

- [ ] **Step 1: Write documentation contract tests.**

Add tests that load both QC skill copies and assert they contain:

```python
required_terms = (
    "mode=proxy",
    "source proxy",
    "preview chunks",
    "qc_report",
    "complete",
    "final export",
)
for term in required_terms:
    assert term in canonical_skill
    assert term in harness_skill
assert canonical_skill == harness_skill
```

Add a project-state test that serializes an `Asset` with
`proxy_status="queued"` and verifies the API exposes status but not a guessed
filesystem path for the proxy.

- [ ] **Step 2: Update the operator/agent copy.**

Document:

1. Source proxies are low-resolution CAS siblings selected only by
   `proxy-edit`/`preview-chunk` emission profiles.
2. `mode=proxy` is still a complete review MP4 and is not interactive scrub.
3. `mode=final` always uses canonical originals.
4. Proxy warm hits may report `policy=skip` or `policy=light`; inspect
   `qc_report.complete` before treating a proxy as fully QC’d.
5. Final QC remains available and uses a duration-aware blackdetect budget;
   a timeout is incomplete diagnostic evidence, not permission to ship
   blindly.
6. Cache eviction protects canonical sources and newest deliverables but may
   remove regenerable source proxies and Remotion/render derivatives.

Keep `skills/qc-standards.md` and
`open_edit/harness_skills/qc-standards.md` byte-identical. Update `docs/MCP.md`
to replace the misleading “proxy = 720p” wording with the actual
`fast_proxy` 640×360 artifact and to explain that source proxies are a
separate host-worker derivative. Do not add a new free-form or MCP command.

Append the source-proxy, QC, and cache environment variables from Tasks 4 and
5 to `.env.example`; retain existing user values and comments.

- [ ] **Step 3: Run documentation and API contract tests.**

```bash
/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest \
  tests/test_mcp_server.py tests/test_serve_projects.py \
  tests/test_serve_asset_proxy_jobs.py \
  -o addopts="" -q
cmp -s skills/qc-standards.md open_edit/harness_skills/qc-standards.md
```

Expected: PASS and byte-identical skill copies.

- [ ] **Step 4: Commit terminology and operator policy.**

```bash
git add .env.example skills/qc-standards.md \
  open_edit/harness_skills/qc-standards.md docs/MCP.md \
  tests/test_mcp_server.py tests/test_serve_projects.py
git commit -m "docs(render): document source-proxy and QC cache policy"
```

---
