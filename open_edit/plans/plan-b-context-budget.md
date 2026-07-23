# Plan B: Context Budget System

## Objective
Add token counting, sliding window history truncation, tool result size caps, fix base64 duplication in `prune_images`, and cap project state size in the system prompt. Eliminate the root cause of the `LimitOverrunError` (oversized conversation history).

## Files affected
- `open_edit/serve/agent.py` — `_make_slim_history` (line 592), `_build_system_prompt` (line 247), `_build_tool_result_message` (line 556), `append_to_conversation` (line 118)
- `open_edit/serve/visual_verify.py` — `prune_images` (line 332), `build_verification_tool_result` (around line 200)
- `open_edit/serve/llm.py` — `_read_with_timeout` (line 589), pi event stream (line 610+)
- `open_edit/serve/pi_bridge.py` — tool result handling

## Problem detail
1. **prune_images strips `type: "image"` blocks but NOT the embedded base64 in `text_summary`** (agent.py:569: `text_summary = json.dumps(result, default=str)` where `result` contains `verification.frames[].data` which is base64 — this data is serialized into `text_summary` even after images are pruned)
2. **No token counting** — the "slim" history is only visually slim; it still carries all tool results in full JSON
3. **No sliding window** — conversation grows unboundedly across turns
4. **Project state in system prompt duplicates tool data** — `_build_system_prompt` dumps the entire project state (60-450KB) even though tools already return this data
5. **Verification frames serialized twice** — once in `text_summary` JSON, once in separate `image` blocks (agent.py:569-576)

---

## Sub-agent breakdown

### Agent B1: Token Counting + Sliding Window
**Scope:** Add a `ContextBudget` module that counts tokens (approximate: 1 token ≈ 4 chars for English text) and truncates history when budget is exceeded. Add `max_history_tokens` env config.

**Specific tasks:**
1. Create `open_edit/serve/context_budget.py`:
   - `count_tokens(text: str) -> int` — approximate: `len(text) // 4`
   - `count_tokens_message(msg: dict) -> int` — recursively count tokens in message content (role + content blocks)
   - `count_tokens_history(history: list[dict]) -> int`
   - `ContextBudget` class with:
     - `max_tokens: int` (default 32000, configurable via `OPEN_EDIT_CONTEXT_MAX_TOKENS`)
     - `reserve_tokens: int` (default 4000, reserved for system prompt + tool schemas)
     - `truncate(history: list[dict]) -> list[dict]` — apply sliding window:
       1. Always keep system message and first user message
       2. Keep last N turns that fit within budget
       3. Replace removed history with `{"role": "user", "content": f"[{n} earlier messages truncated]"}` placeholder
     - `summarize_tool_result(result: dict, max_chars: int = 1000) -> dict` — truncate long string fields, limit list lengths, remove `stdout`/`stderr` over max_chars
2. Update `_make_slim_history` in `agent.py` to:
   - First run `prune_images`
   - Then run `ContextBudget.truncate`
   - Then run `ContextBudget.summarize_tool_result` on oversized tool results
3. Update `_build_system_prompt` in `agent.py` to truncate project state JSON to `max_state_chars` (default 10000). Add `... [state truncated]` marker when cut.
4. Add config env vars to `serve_env.py`:
   - `OPEN_EDIT_CONTEXT_MAX_TOKENS` (default 32000)
   - `OPEN_EDIT_CONTEXT_MAX_STATE_CHARS` (default 10000)
5. Add tests: `tests/test_context_budget.py` with:
   - Basic token counting
   - History truncation preserves first + last N turns
   - Truncation inserts placeholder
   - Tool result summarization
   - Budget enforcement

**Verification:**
- `pytest tests/test_context_budget.py -v` passes
- With a 200KB conversation, `truncate` produces <32K tokens
- With a 100KB project state, system prompt state section is <10K chars

---

### Agent B2: Fix base64 Duplication in prune_images
**Scope:** Fix the critical bug where `prune_images` strips `type: "image"` blocks but leaves embedded base64 data in the `text_summary` JSON string. Also fix the "serialized twice" problem in `_build_tool_result_message`.

**Specific tasks:**
1. Fix `prune_images` in `visual_verify.py`:
   - When stripping `type: "image"` blocks from a tool_result, also strip the `frames` array from the text summary
   - Add a new function `_strip_frames_from_result(result: dict) -> dict` that removes `verification.frames` and stores a summary placeholder
2. Fix `_build_tool_result_message` in `agent.py` (line 556-589):
   - Change `text_summary` to NOT include frame data: strip `verification.frames` before serializing
   - Frame data is already in the separate `type: "image"` blocks — no need to duplicate
   - Add `frame_count` and `render_id` to text summary for context
3. Add `_strip_verification_frames(result: dict) -> dict` helper to avoid code duplication
4. Verify that `prune_images` on a message with verification frames:
   - Removes `type: "image"` blocks ✓ (already works)
   - Results in text_summary that is readable text (no base64 blob) ✓ (new behavior)
5. Add tests: `tests/test_visual_verify_prune.py` with:
   - Message with verification frames → text summary has no base64
   - Message without frames → unchanged
   - Multiple verification rounds → all pruned correctly
   - Stress test: 3 verification rounds with 4 frames each → text summary under 5KB

**Verification:**
- `pytest tests/test_visual_verify_prune.py -v` passes
- A slimmed message with 3 verification rounds of 4 frames each is under 50KB total (currently ~400KB)
- `prune_images` output has no `data:` URLs longer than 200 chars

---

### Agent B3: Oversized Tool Result Handling + LimitOverrunError Guard
**Scope:** Add proactive size limits on tool results before they enter the conversation history. Add a secondary guard for the pi subprocess pipe to prevent `LimitOverrunError` even with oversized output.

**Specific tasks:**
1. Create `open_edit/serve/result_capper.py`:
   - `cap_tool_result(result: dict, max_bytes: int = 512_000) -> dict` — truncate oversized tool results:
     - For dict results: truncate `stdout`, `stderr`, `error` fields to 10K chars each
     - For list results (e.g. asset list, segments): limit to `max_items` (default 20) with `...[N more]` marker
     - For `trigger_render` results: always remove `stdout`/`stderr` (they're for debugging only)
     - Add `_truncated: true` field when truncation occurs
   - Result is called BEFORE `append_to_conversation` and BEFORE yielding `tool_result` event
2. Update `_execute_tool` result handling in `agent.py` (around line 1127 and 1213) to pass through `cap_tool_result`
3. Update `pi_bridge.py` tool dispatch to also cap results (line ~104)
4. Add pi subprocess pipe guard in `llm.py`:
   - `_read_with_timeout` already handles chunks with `read(65536)` and `b"\n".split()` — but add a `max_line_bytes` check
   - If a single line exceeds `max_line_bytes` (default 1MB), log a warning and yield a truncated error event instead of passing the oversized line through
   - This is a defense-in-depth measure — the line-based splitting already prevents `LimitOverrunError` in our code, but a malformed pi output could still cause issues
5. Add tests: `tests/test_result_capper.py` with:
   - Oversized stdout → truncated
   - Long list → capped with marker
   - render result → stdout/stderr removed
   - Small result → unchanged
   - `_truncated` field added correctly

**Verification:**
- `pytest tests/test_result_capper.py -v` passes
- A 2MB tool result becomes <512KB after capping
- Render results never carry stdout/stderr to the LLM
- The pi stream handler gracefully handles a 5MB single NDJSON line

---

## Integration verification (all 3 agents done)
1. Full test suite: `pytest tests/ -v`
2. Stress test: replay the 224KB conversation (79bab7d2-...) through `ContextBudget.truncate` + `prune_images` + `cap_tool_result` and verify output is under 32K tokens
3. System prompt state section under 10K chars
4. No base64 data in slimmed text summaries
5. `test_huge_line_stream.py` still passes (proves 2MB+ lines work)
