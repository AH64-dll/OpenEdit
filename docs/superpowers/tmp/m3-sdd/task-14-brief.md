# Task 14 Brief

### Task 14: Document the new job and preserve the three-product vocabulary

**Files:**
- Modify: `skills/open-edit-mcp.md`
- Modify: `skills/open-edit-mcp-reference.md`
- Modify: `skills/tool_surface.md`
- Modify: `open_edit/harness_skills/open-edit-mcp.md`
- Modify: `open_edit/harness_skills/open-edit-mcp-reference.md`
- Modify: `open_edit/harness_skills/tool_surface.md`
- Modify: `docs/MCP.md`
- Test: `tests/test_mcp_server.py`
- Test: `tests/test_tool_contract.py`

**Interfaces:**
- Consumes: the finalized MCP/REST contracts from Tasks 8–10.
- Produces: synchronized host-facing instructions that say `preview-chunks` is a background range cache, `proxy` is a whole-file artifact, `final` is delivery, and free-form never renders preview media.

- [ ] **Step 1: Write failing documentation-contract tests.**

```python
def test_mcp_playbook_distinguishes_proxy_and_preview_chunks():
    text = Path("skills/open-edit-mcp.md").read_text()
    assert "`preview-chunks`" in text
    assert "whole-file" in text
    assert "audio" in text and "independent" in text
    assert "live MLT" in text and "M4" in text

def test_packaged_skill_matches_canonical_preview_section():
    paths = [
        Path("skills/open-edit-mcp.md"),
        Path("open_edit/harness_skills/open-edit-mcp.md"),
    ]
    for path in paths:
        text = path.read_text()
        assert "`preview-chunks`" in text
        assert "sequential" in text
        assert "same-range" in text
```

- [ ] **Step 2: Run the documentation tests and verify the new wording is missing.**

Run: `pytest tests/test_mcp_server.py tests/test_tool_contract.py -q`

Expected: FAIL on the new assertions only.

- [ ] **Step 3: Update the canonical skill docs.** Add a `preview-chunks` example with ranges/media/priority, explain non-blocking polling and manifest status, describe same-range fallback and stale proxy fallback, show the wipe endpoint, and state that MSE is optional while sequential playback is the M3 default.

- [ ] **Step 4: Synchronize packaged skill copies and update `docs/MCP.md`.** Keep existing proxy/final examples unchanged except for terminology clarifications. Document `OPEN_EDIT_AUTO_PREVIEW`, cache cap/TTL knobs, and the unchanged final workflow.

- [ ] **Step 5: Run documentation/MCP tests and commit.**

Run: `pytest tests/test_mcp_server.py tests/test_tool_contract.py -q`

Expected: PASS.

```bash
git add skills/open-edit-mcp.md skills/open-edit-mcp-reference.md skills/tool_surface.md open_edit/harness_skills/open-edit-mcp.md open_edit/harness_skills/open-edit-mcp-reference.md open_edit/harness_skills/tool_surface.md docs/MCP.md tests/test_mcp_server.py tests/test_tool_contract.py
git commit -m "docs: describe chunked timeline preview workflow"
```
