# Open Edit Experimental Prototype

This directory is **experimental**. It is not the production implementation of `mlt-pipeline`.

The supported production path for this repository is the Go pipeline in `cmd/`, `internal/`, `run.sh`, and `edit.sh`.

Read the boundary and bridge contract before using this code:

- [`../docs/architecture-boundary.md`](../docs/architecture-boundary.md)

## Status

`open_edit/` contains prototype work for a larger AI-native editor:

- Python IR/edit graph code
- asset storage and render/QC helpers
- FastAPI server and static UI
- sandbox experiments
- LLM provider integrations

It may be useful for exploration, but it has a different architecture and maturity level than the Go pipeline.

## Non-goals while experimental

- Do not make production scripts depend on `open_edit` internals.
- Do not treat `open_edit`'s MLT/rendering code as canonical while the Go CLIs own production rendering.
- Do not mutate Go pipeline artifacts in place from this package.

## Bridge rule

If this prototype needs to interoperate with the production pipeline, use the file-based bridge:

1. Read `metadata.json` and `edl.json` as imported snapshots.
2. Export a new file, for example `edl.open_edit.json`.
3. Validate it through the Go bridge helper:

```bash
scripts/validate_open_edit_edl.sh projects/<name> edl.open_edit.json --render
```

Or run the raw production commands:

```bash
bin/compile --edl edl.open_edit.json --metadata metadata.json --output project.open_edit.mlt
bin/render --mlt project.open_edit.mlt --output preview.open_edit.mp4 --dry-run --timeout 10m
```

Only validated artifacts should be promoted back to `edl.json` or `project.mlt`.
