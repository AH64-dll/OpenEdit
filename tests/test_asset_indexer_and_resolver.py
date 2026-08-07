"""
Unit tests for open_edit.asset_indexer and open_edit.asset_resolver.
"""

import json
import os
import pytest
from open_edit.asset_indexer import generate_manifest, index_assets
from open_edit.asset_resolver import AssetResolver, get_resolver


def test_asset_indexer_and_resolver(tmp_path):
    # Setup test assets directory structure
    assets_dir = tmp_path / "assets"
    sfx_dir = assets_dir / "audio" / "sfx"
    sfx_dir.mkdir(parents=True, exist_ok=True)
    
    overlay_dir = assets_dir / "video" / "overlays"
    overlay_dir.mkdir(parents=True, exist_ok=True)

    # Create dummy files
    (sfx_dir / "sfx_impact_heavy_explosion_01.wav").write_text("dummy audio")
    (sfx_dir / "sfx_whoosh_fast_air_01.wav").write_text("dummy audio")
    (overlay_dir / "vfx_overlay_light_leak_warm_4k.mov").write_text("dummy video")

    # Generate manifest
    manifest_path = tmp_path / "assets_manifest.json"
    out_file = generate_manifest(str(assets_dir), str(manifest_path))

    assert os.path.exists(out_file)

    with open(out_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["total_assets"] == 3
    assets = data["assets"]
    asset_ids = [a["asset_id"] for a in assets]
    assert "sfx_impact_heavy_explosion_01" in asset_ids
    assert "sfx_whoosh_fast_air_01" in asset_ids
    assert "vfx_overlay_light_leak_warm_4k" in asset_ids

    # Test Resolver
    resolver = AssetResolver(manifest_path=str(manifest_path))

    # Test trigger resolution
    whoosh_asset = resolver.resolve_by_trigger("scene_transition")
    assert whoosh_asset is not None
    assert whoosh_asset["asset_id"] == "sfx_whoosh_fast_air_01"

    # Test category resolution
    sfx_assets = resolver.resolve(category="audio", subcategory="sfx")
    assert len(sfx_assets) == 2

    # Test natural language query
    explosion_query = resolver.query("We need a massive explosion hit")
    assert len(explosion_query) > 0
    assert explosion_query[0]["asset_id"] == "sfx_impact_heavy_explosion_01"


if __name__ == "__main__":
    test_asset_indexer_and_resolver(tmp_path=Path("/tmp/test_assets_env"))
    print("✅ All asset indexer and resolver tests passed successfully!")
