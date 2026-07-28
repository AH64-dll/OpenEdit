"""Load the effect catalog from a directory of YAML files."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class ParamSpec(BaseModel):
    type: Literal["float", "int", "str", "bool"]
    default: float | int | str | bool | None = None
    range: list[float] | None = None
    unit: str | None = None


class EffectSpec(BaseModel):
    name: str
    mlt_service: str
    target_kind: list[Literal["clip", "track"]]
    params: dict[str, ParamSpec] = Field(default_factory=dict)
    keyframe_params: list[str] = Field(default_factory=list)
    interp: list[Literal["linear", "discrete", "smooth"]] = Field(default_factory=list)
    description: str = ""


class EffectCatalog:
    """In-memory registry of effect specs loaded from YAML."""

    def __init__(self, catalog_dir: str | Path):
        self.catalog_dir = Path(catalog_dir)
        self._specs: dict[str, EffectSpec] = {}
        self._load()

    def _load(self) -> None:
        effects_dir = self.catalog_dir / "effects"
        if not effects_dir.exists():
            return
        for path in sorted(effects_dir.glob("*.yaml")):
            with open(path) as f:
                data = yaml.safe_load(f)
            spec = EffectSpec(**data)
            self._specs[spec.name] = spec

    def is_known(self, effect_type: str) -> bool:
        return effect_type in self._specs

    def get(self, effect_type: str) -> EffectSpec | None:
        return self._specs.get(effect_type)

    def known_names(self) -> set[str]:
        return set(self._specs.keys())
