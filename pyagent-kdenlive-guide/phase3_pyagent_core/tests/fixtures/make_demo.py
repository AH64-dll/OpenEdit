"""Generate tests/fixtures/demo.kdenlive — a tiny but real Kdenlive project.

Used by the runtime tests as a known-good starting point. Built by calling
Phase 2's KdenliveFileBackend with a 10-second test clip.
"""
import sys
from pathlib import Path

# make_demo.py lives at: <mlt-pipeline>/pyagent-kdenlive-guide/phase3_pyagent_core/tests/fixtures/make_demo.py
# parents[3] is pyagent-kdenlive-guide (Phase 2's location); parents[4] is mlt-pipeline (testdata lives there).
PROJECT_ROOT = Path(__file__).resolve().parents[3]
MLT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))

from phase2_project_engine import KdenliveFileBackend, Catalog  # noqa: E402

CATALOG = PROJECT_ROOT / "phase1_knowledge_base" / "catalog.json"
CLIP = MLT_ROOT / "testdata" / "clip_short.mp4"
OUT = Path(__file__).resolve().parent / "demo.kdenlive"


def main() -> None:
    if not CLIP.exists():
        sys.exit(f"missing test clip at {CLIP}; expected from mlt-pipeline/testdata/")
    cat = Catalog.from_json(str(CATALOG))
    backend = KdenliveFileBackend(project_path=None, catalog=cat)
    src_id = backend.import_media([str(CLIP)])[0]
    backend.append_clip(0, src_id, 0.0, 4.0)
    backend.save(str(OUT))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
