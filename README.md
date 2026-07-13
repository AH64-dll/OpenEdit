# mlt-pipeline

Autonomous video-editing pipeline. Raw footage → Kdenlive-editable `project.mlt` via an OpenCode-driven agent.

See `docs/superpowers/specs/2026-07-13-mlt-pipeline-design.md` for design.
See `docs/superpowers/plans/2026-07-13-mlt-pipeline-impl.md` for implementation plan.

## Quickstart

```bash
# Stage 1: deterministic core
go test ./...

# Stage 2: end-to-end with hand-written EDL
./bin/analyze testdata/clip_short.mp4 --output testdata/clip_short.metadata.json
./bin/compile --edl testdata/clip_short.edl.handwritten.json \
              --metadata testdata/clip_short.metadata.json \
              --output testdata/clip_short.project.mlt
./bin/render --mlt testdata/clip_short.project.mlt \
             --output testdata/clip_short.expected.preview.mp4 --dry-run

# Stage 3: full agent loop
./run.sh my-project
```
