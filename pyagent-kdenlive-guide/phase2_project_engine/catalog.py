"""In-memory snapshot of Phase 1's catalog.json."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Catalog:
    effects: list[dict]
    transitions: list[dict]
    generators: list[dict]
    by_id: dict[str, dict] = field(default_factory=dict)

    @classmethod
    def from_json(cls, path: str | Path) -> "Catalog":
        data = json.loads(Path(path).read_text())
        by_id: dict[str, dict] = {}
        for e in data["effects"] + data["transitions"] + data["generators"]:
            kid = e.get("kdenlive_id")
            if kid:
                by_id[kid] = e
        return cls(
            effects=data["effects"],
            transitions=data["transitions"],
            generators=data["generators"],
            by_id=by_id,
        )


__all__ = ["Catalog"]
