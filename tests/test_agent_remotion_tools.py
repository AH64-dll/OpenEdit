"""Functional coverage for Remotion TOOL_TABLE wrappers."""
from __future__ import annotations

from pathlib import Path

from open_edit.agent.tools.pyagent_generate_remotion_composition import (
    generate_remotion_composition,
)
from open_edit.agent.tools.pyagent_init_remotion_project import init_remotion_project
from open_edit.agent.tools.pyagent_write_remotion_composition import (
    write_remotion_composition,
)
from open_edit.storage.edit_graph import EditGraphStore


def test_remotion_tools_scaffold_write_and_append_graph_op(tmp_path: Path) -> None:
    initialized = init_remotion_project({}, str(tmp_path))
    assert initialized["status"] == "ok"
    root = Path(initialized["remotion_root"])
    assert (root / "src" / "index.ts").is_file()
    EditGraphStore(tmp_path / ".open_edit" / "edit_graph.db")

    written = write_remotion_composition(
        {
            "relative_path": "src/compositions/Hello.tsx",
            "source": "export const Hello = () => null;\n",
        },
        str(tmp_path),
    )
    assert written["status"] == "ok"
    assert (root / "src" / "compositions" / "Hello.tsx").read_text() == (
        "export const Hello = () => null;\n"
    )

    generated = generate_remotion_composition(
        {
            "composition_id": "Hello",
            "entry_point": "src/index.ts",
            "duration_sec": 2,
            "props": {"text": "hello"},
        },
        str(tmp_path),
    )
    assert generated["status"] == "ok", generated
    assert generated["clip_id"]
    ops = EditGraphStore(tmp_path / ".open_edit" / "edit_graph.db").load_all()
    assert any(getattr(op, "kind", "") == "add_remotion_composition" for op in ops)
