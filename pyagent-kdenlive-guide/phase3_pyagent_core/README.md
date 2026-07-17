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
   pyagent_runtime` is importable from anywhere.

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

## See also

- `DESIGN.md` — the design spec
- `../PHASE_3_pyagent_core.md` — the phase requirements
