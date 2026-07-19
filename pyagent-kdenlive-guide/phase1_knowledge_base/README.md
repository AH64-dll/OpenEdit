# phase1_knowledge_base

Static knowledge assets for the pyagent toolchain. Currently: a single
MLT/effect/transition catalog (built once from the Kdenlive source
tree) that the rest of the pipeline reads at startup.

## What it is

Phase 1 owns the read-only reference data: the list of available
effects, transitions, and their default parameters. Phase 3
(`phase3_pyagent_core/catalog_slice.py`) loads it on import and the
LLM's `pyagent_list_catalog` tool reads the in-memory slice.

## File map

| File | Purpose | Size |
|---|---|---|
| `build_catalog.py` | Build script: scrapes Kdenlive's installed effect/transition XMLs into `catalog.json` | 285 lines |
| `catalog.json` | The catalog itself (effect id → default params, transition id → kind) | 673 KB |

## Build

```bash
cd pyagent-kdenlive-guide
python3 phase1_knowledge_base/build_catalog.py
# writes phase1_knowledge_base/catalog.json
```

The build reads Kdenlive's installed `.xml` profiles from
`/usr/share/kdenlive/effects/` and `/usr/share/kdenlive/transitions/`
(filtered by `version >= 17.04`). It is deterministic and idempotent;
running it twice produces a byte-identical `catalog.json`.

## Test

Phase 1 has no test module of its own — it is exercised by every
Phase 2 / Phase 3 test that calls a method on a clip with a
catalog-defined effect or transition. If `catalog.json` is missing,
~15 tests across Phase 2 and Phase 3 fail with `FileNotFoundError`.
