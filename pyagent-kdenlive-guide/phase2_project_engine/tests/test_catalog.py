import json
import pytest
from phase2_project_engine.catalog import Catalog


@pytest.fixture
def sample_catalog_json(tmp_path):
    p = tmp_path / "cat.json"
    p.write_text(json.dumps({
        "effects": [
            {"kdenlive_id": "blur", "mlt_service": "boxblur",
             "name": "Blur", "parameters": [{"name": "sigma", "type": "double"}]},
        ],
        "transitions": [
            {"kdenlive_id": "dissolve", "mlt_service": "mix", "name": "Dissolve"},
        ],
        "generators": [
            {"kdenlive_id": "color", "mlt_service": "color", "name": "Color"},
        ],
    }))
    return p


def test_load_from_json(sample_catalog_json):
    cat = Catalog.from_json(str(sample_catalog_json))
    assert cat.effects[0]["kdenlive_id"] == "blur"
    assert cat.transitions[0]["kdenlive_id"] == "dissolve"


def test_lookup_by_id(sample_catalog_json):
    cat = Catalog.from_json(str(sample_catalog_json))
    assert cat.by_id["blur"]["mlt_service"] == "boxblur"
    assert cat.by_id["dissolve"]["mlt_service"] == "mix"
    assert cat.by_id["color"]["mlt_service"] == "color"


def test_lookup_missing_returns_none(sample_catalog_json):
    cat = Catalog.from_json(str(sample_catalog_json))
    assert cat.by_id.get("nonexistent") is None
