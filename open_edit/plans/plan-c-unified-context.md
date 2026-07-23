# Plan C: Unified Context + State

## Objective
Eliminate dual-store desync between our JSONL and pi's session file, fix stale system prompt within turns, deduplicate state from system prompt, and pass conversation history to pi via STDIN instead of letting pi manage its own session file.

## Files affected
- `open_edit/serve/agent.py` — `_run_cli_owned_turn` (line 627), `_build_system_prompt` (line 247), conversation persistence (lines 88–130), `append_to_conversation` (line 118), `load_conversation` (line 98)
- `open_edit/serve/llm.py` — `stream_chat` (around line 200), `_stream_pi` (around line 400), `_stream_cli` (line 511)
- `open_edit/serve/pi_bridge.py` — entire file (lines 1–416), tool dispatch (line 102)
- `open_edit/serve/cli_adapter.py` — `PiAdapter.build_command` (around line 60)
- `open_edit/serve/providers.py` — `resolve_provider` (around line 50)
- `open_edit/serve/visual_verify.py` — `build_verification_tool_result` (around line 200)

## Problem detail
1. **Dual-store desync**: Our JSONL at `.open_edit/conversations/<conv_id>.jsonl` and pi's session file at `~/.pi/sessions/<id>.jsonl` grow independently. After a crash or restart, the two can diverge.
2. **Stale system prompt within turns**: `_build_system_prompt` is called once per turn (agent.py:647). If a tool mutation changes project state within a turn, subsequent tool calls in the same turn operate on stale system prompt state.
3. **Duplicate state in system prompt**: Project state dump (60-450KB) in `_build_system_prompt` duplicates data that tools (like `list_assets`, `get_pending_notes`) already return. The LLM receives the same data twice.
4. **Conversation history passed via file, not STDIN**: For SDK providers, history is loaded from JSONL and passed in `messages`. For pi, pi manages its own session file. This means pi doesn't see the messages our JSONL has (and vice versa on next turn).

---

## Sub-agent breakdown

### Agent C1: Eliminate Dual-Store Desync — Make JSONL the Single Source of Truth
**Scope:** Ensure pi receives conversation history from our JSONL (via STDIN) instead of managing its own session file. This eliminates the dual-store problem entirely.

**Specific tasks:**
1. Add `--session-file` or `--history` flag support to `cli_adapter.py` `PiAdapter`:
   - Option A: If pi supports passing history as a file, pass our JSONL path
   - Option B: More likely — pass history inline via a system message or the initial prompt
   - Check pi's CLI help: `pi --help` to see if `--session` or `--history` flags exist
2. If pi doesn't support external history injection, add a `pi_extension` message that seeds pi's session state before the conversation starts
3. Ensure `append_to_conversation` is called BEFORE the next pi subprocess invocation, so pi always sees the latest history
4. Remove or disable pi's independent session file management:
   - In `extension.ts`, check if we can prevent pi from writing its own session file
   - If not, ensure our JSONL is the authoritative copy and pi's session file is treated as a cache that can be regenerated
5. Add reconciliation on server startup:
   - On server start, check if JSONL and pi session file are in sync
   - If not, rebuild pi session file from our JSONL (authoritative)
6. Update `_run_cli_owned_turn` to:
   - Save to JSONL AFTER each tool result is received from pi (not just at turn end)
   - This way if pi crashes mid-turn, our JSONL has partial progress
7. Add tests: `tests/test_conversation_sync.py` with:
   - History saved to JSONL after each tool_result
   - Pi session rebuild from JSONL on restart
   - Crash recovery: kill pi mid-turn, verify JSONL has partial results

**Verification:**
- After a pi turn, the JSONL has all messages (including tool_use/tool_result pairs)
- After server restart, pi can continue the conversation from JSONL
- No divergence between JSONL and what pi sees

---

### Agent C2: Fix Stale System Prompt Within Turns + Deduplicate State
**Scope:** Refresh system prompt project state after each mutation within a turn. Deduplicate project state — remove it from the system prompt when tools already return it. Add an "executive summary" instead of the full state dump.

**Specific tasks:**
1. Modify `_build_system_prompt` to accept an optional `state_summary_only: bool`:
   - When `True`: replace the full project state JSON dump with a brief summary:
     - `Asset count: N`
     - `Track count: N`
     - `Last op type: <kind>`
     - `Pending notes: N`
   - When `False`: keep the full state dump for the initial prompt of each turn
2. Add `_build_state_summary(state) -> str` helper that produces a 3-5 line summary
3. In `_run_agent_turn` (the SDK-owned provider loop, not the CLI-owned one):
   - After each tool execution, update the system prompt's state section
   - For the NEXT LLM call in the same turn, use `state_summary_only=True`
   - This means the first LLM call gets full state; subsequent calls in the same turn get a summary
4. For `_run_cli_owned_turn` (pi path):
   - Inject project state summary as a system message or as part of the user message after each tool result
   - This refreshes pi's context after each mutation
5. Add tests: `tests/test_system_prompt.py` with:
   - Full state prompt contains expected keys
   - Summary prompt is <1KB
   - Multiple tool calls in one turn don't degrade in quality (subjective, check token count)
   - Summary prompt doesn't omit critical state (like project_id)

**Verification:**
- System prompt with `state_summary_only=True` is under 1KB (vs 60-450KB)
- After a tool mutation in an SDK turn, the next LLM call receives updated state summary
- All tests pass

---

### Agent C3: Conversation History Cleanup + Efficient Serialization
**Scope:** Add conversation history compaction, remove unnecessary messages, and reduce per-message overhead. Ensure history stays lean even across many turns.

**Specific tasks:**
1. Add `compact_history(history: list[dict]) -> list[dict]` to `context_budget.py`:
   - Merge consecutive `user` messages (from tool results) into a single message
   - Remove assistant messages that only contain `tool_use` blocks with no text (common pi pattern)
   - Keep the last N actual user messages (N configurable, default 5)
   - Remove `stdout`/`stderr` from tool results (they're debug info, not LLM-facing)
2. Implement history compaction in `_make_slim_history`:
   - Run compact → prune_images → ContextBudget.truncate → cap tool results
3. Add periodic compaction on conversation save:
   - In `append_to_conversation`, every 50th append triggers an async compaction job
   - Compaction rewrites the JSONL file in-place (atomic: write to temp, replace)
4. Fix the per-message format to reduce overhead:
   - Current format: `{"role": "user", "content": [{"type": "tool_result", "tool_use_id": "...", "content": "..."}]}`
   - This wraps every tool_result in a list of one block — unnecessary overhead
   - Simplify: when content is a single text string, use `{"role": "user", "content": "..."}` (string, not list)
   - Keep list form only when there are multiple content blocks (e.g. text + image)
   - This reduces per-message bytes by ~30%
5. Add tests: `tests/test_history_compaction.py` with:
   - Consecutive user messages merged
   - Text-only assistant messages preserved (tool-only messages removed)
   - 10-turn conversation compacted to under 50K tokens
   - JSONL rewrite doesn't lose data
   - Atomic write safety (crash mid-write keeps original intact)

**Verification:**
- A 10-turn conversation fits in <50K tokens (currently ~200K+)
- `append_to_conversation` never blocks on compaction (runs async)
- All existing tests pass
- History roundtrip: compact → load → compact produces same result

---

## Integration verification (all 3 agents done)
1. Full test suite: `pytest tests/ -v`
2. Manual test: start server, have a 5-turn conversation, verify JSONL is the single truth
3. Crash test: kill server mid-turn, restart, verify conversation continues from JSONL
4. Token verification: system prompt <1KB (summary mode), conversation <32K tokens (after budget)
5. Pi session file is empty or matches JSONL exactly
