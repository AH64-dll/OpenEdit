"""Tests for Remotion scaffold + import safety."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from open_edit.render.remotion_scaffold import (
    ensure_remotion_scaffold,
    validate_composition_source,
    write_composition_file,
)


def test_ensure_scaffold_idempotent(tmp_path: Path) -> None:
    root = ensure_remotion_scaffold(tmp_path)
    assert (root / "src" / "index.ts").is_file()
    assert (root / "src" / "compositions" / "TitleCard.tsx").is_file()
    assert (root / "LICENSE_NOTICE.txt").is_file()
    # Second call does not overwrite custom edits
    (root / "src" / "index.ts").write_text("custom\n")
    ensure_remotion_scaffold(tmp_path)
    assert (root / "src" / "index.ts").read_text() == "custom\n"


def test_scaffold_pins_programmatic_renderer_packages(tmp_path: Path) -> None:
    root = ensure_remotion_scaffold(tmp_path)
    package = json.loads((root / "package.json").read_text(encoding="utf-8"))

    assert package["dependencies"]["@remotion/bundler"] == "4.0.278"
    assert package["dependencies"]["@remotion/renderer"] == "4.0.278"


def test_validate_rejects_fs_import() -> None:
    errs = validate_composition_source('import fs from "fs";\nexport const X = 1;\n')
    assert errs


def test_write_composition_ok(tmp_path: Path) -> None:
    src = (
        'import React from "react";\n'
        'import { AbsoluteFill } from "remotion";\n'
        "export const Hello = () => <AbsoluteFill>Hi</AbsoluteFill>;\n"
    )
    path = write_composition_file(tmp_path, "src/compositions/Hello.tsx", src)
    assert path.is_file()


def test_write_composition_rejects_escape(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="relative"):
        write_composition_file(tmp_path, "../evil.tsx", 'export const X = 1;\n')
