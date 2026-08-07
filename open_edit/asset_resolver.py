"""
Asset Resolver Module for OpenEdit / mlt-pipeline.

Provides semantic asset retrieval for AI agents and the MLT render pipeline.
Resolves natural language queries, triggers, categories, and tags to indexed media assets.
"""

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


class AssetResolver:
    """Interface for querying and resolving media assets from open_edit/assets_manifest.json."""

    def __init__(self, manifest_path: str = "open_edit/assets_manifest.json"):
        self.manifest_path = manifest_path
        self.assets: List[Dict[str, Any]] = []
        self.load_manifest()

    def load_manifest(self) -> None:
        """Loads assets from the JSON manifest file."""
        if not os.path.exists(self.manifest_path):
            self.assets = []
            return

        try:
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.assets = data.get("assets", [])
        except (json.JSONDecodeError, OSError):
            self.assets = []

    def resolve_by_trigger(self, trigger_name: str, media_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Finds the best matching asset for a given AI trigger event."""
        trigger_lower = trigger_name.lower().strip()
        candidates = []

        for asset in self.assets:
            if media_type and asset.get("media_type") != media_type:
                continue

            triggers = [t.lower() for t in asset.get("ai_triggers", [])]
            if trigger_lower in triggers:
                candidates.append(asset)

        return candidates[0] if candidates else None

    def resolve(
        self,
        category: Optional[str] = None,
        subcategory: Optional[str] = None,
        tags: Optional[List[str]] = None,
        media_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Filters assets by category, subcategory, tags, or media_type."""
        results = []
        req_tags = set(t.lower() for t in tags) if tags else set()

        for asset in self.assets:
            if category and asset.get("category", "").lower() != category.lower():
                continue
            if subcategory and asset.get("subcategory", "").lower() != subcategory.lower():
                continue
            if media_type and asset.get("media_type", "").lower() != media_type.lower():
                continue

            if req_tags:
                asset_tags = set(t.lower() for t in asset.get("tags", []))
                if not req_tags.intersection(asset_tags):
                    continue

            results.append(asset)

        return results

    def query(self, prompt_text: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Ranks and retrieves top assets matching a natural language prompt."""
        tokens = set(re.findall(r"\w+", prompt_text.lower()))
        scored_assets = []

        for asset in self.assets:
            score = 0
            asset_id = asset.get("asset_id", "").lower()
            tags = set(t.lower() for t in asset.get("tags", []))
            triggers = set(t.lower() for t in asset.get("ai_triggers", []))
            file_path = asset.get("file_path", "").lower()

            for token in tokens:
                if len(token) <= 2:
                    continue
                if token in asset_id:
                    score += 5
                if token in tags:
                    score += 3
                if token in triggers:
                    score += 4
                if token in file_path:
                    score += 2

            if score > 0:
                scored_assets.append((score, asset))

        scored_assets.sort(key=lambda x: x[0], reverse=True)
        return [asset for _, asset in scored_assets[:limit]]


# Module-level convenience functions
_default_resolver: Optional[AssetResolver] = None


def get_resolver(manifest_path: str = "open_edit/assets_manifest.json") -> AssetResolver:
    global _default_resolver
    if _default_resolver is None or _default_resolver.manifest_path != manifest_path:
        _default_resolver = AssetResolver(manifest_path)
    return _default_resolver
