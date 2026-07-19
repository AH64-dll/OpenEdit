"""Tests for the EffectCatalog (YAML registry + validation gate)."""
from pathlib import Path

import pytest

from open_edit.ir.catalog.loader import EffectCatalog, EffectSpec


@pytest.fixture
def catalog_dir(tmp_path: Path) -> Path:
    d = tmp_path / "catalog" / "effects"
    d.mkdir(parents=True)
    (d / "volume.yaml").write_text("""
name: volume
mlt_service: volume
target_kind: [clip, track]
params:
  gain:
    type: float
    default: 1.0
    range: [0.0, 4.0]
    unit: linear
keyframe_params: [gain]
interp: [linear, discrete]
description: "Audio volume control. gain=1.0 is unity."
""")
    (d / "brightness.yaml").write_text("""
name: brightness
mlt_service: brightness
target_kind: [clip]
params:
  value:
    type: float
    default: 0.0
    range: [-1.0, 1.0]
keyframe_params: [value]
interp: [linear, discrete]
description: "Brightness adjustment."
""")
    return tmp_path / "catalog"


def test_catalog_loads_all_yaml_files(catalog_dir: Path) -> None:
    cat = EffectCatalog(catalog_dir)
    assert cat.is_known("volume") is True
    assert cat.is_known("brightness") is True
    assert cat.is_known("nonexistent") is False


def test_catalog_get_returns_spec(catalog_dir: Path) -> None:
    cat = EffectCatalog(catalog_dir)
    spec = cat.get("volume")
    assert spec is not None
    assert spec.name == "volume"
    assert spec.mlt_service == "volume"
    assert "clip" in spec.target_kind
    assert "track" in spec.target_kind
    assert "gain" in spec.params


def test_catalog_returns_none_for_unknown(catalog_dir: Path) -> None:
    cat = EffectCatalog(catalog_dir)
    assert cat.get("unknown") is None


def test_catalog_known_names(catalog_dir: Path) -> None:
    cat = EffectCatalog(catalog_dir)
    assert set(cat.known_names()) == {"volume", "brightness"}


def test_catalog_handles_empty_directory(tmp_path: Path) -> None:
    d = tmp_path / "empty_catalog" / "effects"
    d.mkdir(parents=True)
    cat = EffectCatalog(tmp_path / "empty_catalog")
    assert cat.known_names() == set()


def test_bundled_catalog_has_all_spec_required_effects() -> None:
    """Bug-hunt finding: the bundled catalog must contain all 10
    spec-required effects (volume, brightness, contrast, saturation,
    panner, eq, gain, delay, luma, dissolve)."""
    from pathlib import Path
    bundled = Path(__file__).parent.parent.parent / "open_edit" / "ir" / "catalog"
    cat = EffectCatalog(bundled)
    required = {
        "volume", "brightness", "contrast", "saturation",
        "panner", "eq", "gain", "delay", "luma", "dissolve",
    }
    assert required.issubset(cat.known_names()), (
        f"missing effects: {required - cat.known_names()}"
    )
