# testdata/

Synthetic media fixtures for the Open Edit test suite. Everything here is
reproducible. The mp4 files are small (21-70 KB) synthetic clips generated
with `ffmpeg`; the JSON fixtures are hand-constructed or derived from code.

## testdata/clip_short.mp4

10-second 1920x1080@30fps synthetic clip with two scene cuts at ~4s and ~7s
(blue/green/red color blocks, no audio). Used by `tests/test_serve_asset_stream.py`
(asset upload / streaming / content-type tests).

Regenerate:

```bash
ffmpeg -y -f lavfi -i "color=c=blue:s=1920x1080:r=30:d=4,format=yuv420p" \
       -f lavfi -i "color=c=green:s=1920x1080:r=30:d=3,format=yuv420p" \
       -f lavfi -i "color=c=red:s=1920x1080:r=30:d=3,format=yuv420p" \
       -filter_complex "[0][1][2]concat=n=3:v=1:a=0[v]" \
       -map "[v]" clip_short.mp4
```

## testdata/video_with_audio.mp4

3-second 320x240@25fps synthetic clip with a 440 Hz sine-wave audio track
(h264 + aac). Used as the "fake Remotion output" media in
`tests/test_remotion_ir_materialize.py` and `tests/test_remotion_proxy_golden.py`:
the fake Remotion CLI copies it to the render output path so the materialize
ingest step (which runs ffprobe) accepts the produced file.

Regenerate:

```bash
ffmpeg -y -f lavfi -i "color=c=gray:s=320x240:r=25:d=3,format=yuv420p" \
       -f lavfi -i "sine=frequency=440:duration=3" \
       -shortest -c:v libx264 -preset ultrafast -c:a aac \
       -movflags +faststart video_with_audio.mp4
```

## tests/testdata/raw_videos/

Three 2-second 320x240@25fps h264 clips (`clip_a.mp4`, `clip_b.mp4`,
`clip_c.mp4`, no audio). Used as generic ingest input by the CLI/e2e/storage
tests (`tests/test_cli.py`, `tests/test_e2e.py`, `tests/test_e2e_render.py`,
`tests/test_storage/test_assets.py`, `tests/test_render/test_orchestrator.py`,
`tests/test_render/test_validators.py`, `tests/test_qc/test_gate.py`,
`tests/test_pyagent_import_asset.py`). Tests only require the files to be
valid h264 video that ffprobe can parse; the pixel content is not pinned.

Regenerate each (e.g. `clip_a.mp4`):

```bash
ffmpeg -y -f lavfi -i "color=c=gray:s=320x240:r=25:d=2,format=yuv420p" \
       -c:v libx264 -preset ultrafast -movflags +faststart clip_a.mp4
```

## tests/testdata/golden_11clip/

Hand-constructed golden edit graph (`edit_graph.json`: 11 clips across 1 video
track with 10 transitions) plus the expected derived timeline
(`expected_timeline.json`). `tests/test_render/test_golden_fixtures.py` derives
the timeline from the edit graph and asserts it matches the golden file
byte-for-byte, so a regression in `derive_timeline` surfaces as a diff.

Regenerate `expected_timeline.json` from `edit_graph.json`:

```bash
python3 -c "
import json
from pathlib import Path
from open_edit.ir.types import Project
from pydantic import TypeAdapter
from open_edit.ir.apply import derive_timeline
G = Path('tests/testdata/golden_11clip')
project = TypeAdapter(Project).validate_python(json.loads((G / 'edit_graph.json').read_text()))
tl = derive_timeline(project)
(G / 'expected_timeline.json').write_text(
    json.dumps(tl.model_dump(mode='json'), sort_keys=True, indent=2) + '\n')
"
```
