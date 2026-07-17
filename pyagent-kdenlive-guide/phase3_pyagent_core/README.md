# pyagent — pi extension for Kdenlive editing

A pi extension that gives pi 13 video-editor tools, backed by Phase 2's
`KdenliveFileBackend`. pi handles the LLM; this extension just bridges
LLM tool calls to file edits.

## Install

```bash
cd pyagent-kdenlive-guide/phase3_pyagent_core
make install
```

This:
1. Symlinks the extension into `~/.pi/agent/extensions/pyagent/` so pi
   auto-discovers it.
2. Installs the Python runtime in editable mode so `python3 -m
   phase3_pyagent_core` is importable from anywhere.

## Use

```bash
export PYAGENT_PROJECT=/path/to/your.kdenlive
export PYAGENT_AUTO_APPROVE=false    # default; prompts before each mutating tool
pi    # the pyagent_* tools appear in the tool palette
```

## Test

```bash
make test
```

The runtime tests need no pi or LLM. The integration test needs an LLM
provider configured (e.g., `OPENAI_API_KEY` or `GEMINI_API_KEY`) and
will skip if none is set.

## Test output

```text
test_append_clip_after_import ... ok
test_apply_effect_with_invalid_id_returns_fix_hint ... ok
test_apply_effect_with_valid_id ... ok
... (~30 tests, 0 failures)
test_full_crossfade_chain ... ok
test_help_flag_prints_usage ... ok
test_humanize_no_args ... ok
test_prompt_contains_catalog_slice ... ok
... (extension tests, ~6 tests)
test_crossfade_chain_runs_end_to_end ... SKIPPED (no provider)
```

## See also

- `DESIGN.md` — the design spec
- `../PHASE_3_pyagent_core.md` — the phase requirements
