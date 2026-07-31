# Architecture Boundary: Go Pipeline vs. Open Edit

This repository currently contains two systems with different maturity levels.

## Production path: Go `mlt-pipeline`

The supported production pipeline is the Go flow:

```text
footage/* -> bin/analyze -> metadata.json -> agent writes edl.json -> bin/compile -> project.mlt -> bin/render -> preview.mp4/final.mp4
```

Authoritative files:

- `cmd/` and `internal/`
- `run.sh` and `edit.sh`
- `prompts/edl_writer.md`
- `test/` and `testdata/`

This path is deterministic except for the agent writing `edl.json`. It is covered by `go test ./...`.

## Experimental path: `open_edit/`

`open_edit/` is an experimental product prototype for a larger AI-native editor. It includes a Python IR, asset store, server/UI code, QC/render helpers, sandbox work, and LLM provider integrations.

It is **not** the production implementation of `mlt-pipeline` and must not be treated as a replacement for the Go CLIs until it has its own green test suite, release process, and explicit bridge compatibility tests.

Rules while both live in this repo:

1. Production scripts must call the Go binaries, not Python `open_edit` internals.
2. `open_edit/` may read artifacts emitted by the Go pipeline only through the bridge contract below.
3. `open_edit/` must not mutate `metadata.json`, `edl.json`, or `project.mlt` in place. If it needs to produce new edits, it writes a new EDL file and asks the Go `compile` step to validate it.
4. Shared behavior belongs in documented artifact contracts, not duplicate hidden implementations.
5. README/setup instructions must clearly separate production setup from experimental setup.

## Bridge contract

The bridge is file-based and intentionally narrow.

### Go pipeline exports

A project directory may contain:

- `metadata.json`: canonical media manifest from `bin/analyze`.
- `edl.json`: canonical edit decision list accepted by `bin/compile`.
- `project.mlt`: generated render/Kdenlive artifact. It is a derived file, never the source of truth.
- `preview.mp4` or `final.mp4`: rendered outputs from `bin/render`.

### `open_edit/` may import

`open_edit/` may import `metadata.json` as read-only source metadata. It may import `edl.json` as a snapshot of a Go-pipeline edit, but any richer IR edit graph is experimental state owned by `open_edit/`.

### `open_edit/` may export

If `open_edit/` wants to hand work back to the production pipeline, it must export an EDL-compatible JSON file such as:

```text
projects/<name>/edl.open_edit.json
```

Then the production validator must be run explicitly, either through the helper:

```bash
scripts/validate_open_edit_edl.sh projects/<name> edl.open_edit.json --render
```

Or through the raw Go commands:

```bash
bin/compile --edl edl.open_edit.json --metadata metadata.json --output project.open_edit.mlt
bin/render --mlt project.open_edit.mlt --output preview.open_edit.mp4 --dry-run --timeout 10m
```

Only after these commands pass may a user replace `edl.json` or `project.mlt`.

## Migration decision point

Before `open_edit/` can become production, it needs:

- A documented import/export bridge test against `metadata.json` and `edl.json`.
- A default test command that passes from a clean checkout.
- A statement of which code owns rendering, asset storage, and LLM orchestration.
- Removal or consolidation of duplicate render/analyze logic.

Until then, `open_edit/` remains quarantined experimental code and the Go pipeline remains the supported architecture.
