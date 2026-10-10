"""Agent skills must match the real tool surface and stay small.

These guard the failure modes found in the 2026-10 audit: skills naming fields
or operations that do not exist, drifted packaged copies, and token bloat.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from open_edit.ir.api import IR
from open_edit.kernel import pillar_tools
from open_edit.kernel.tool_registry import EditProjectArgs, QueryProjectArgs
from open_edit.mcp.adapters import mcp_tool_schemas
from open_edit.mcp.skills import (
    LEGACY_STEMS,
    MCP_SKILL_STEMS,
    load_skill,
    mcp_instructions,
    skill_description,
    stem_from_uri,
)

ROOT = Path(__file__).resolve().parents[1]
SKILLS = {stem: load_skill(stem) for stem in MCP_SKILL_STEMS}
ALL_TEXT = "\n".join(SKILLS.values())
OPS = SKILLS["open-edit-ops"]
# Operations handled inline in dispatch_edit rather than through _EDIT_ROUTING.
INLINE_OPS = set(re.findall(r"['\"]([a-z_]+)['\"]", " ".join(
    re.findall(r"^\s*if operation (?:==|in) (.+):$", Path(pillar_tools.__file__).read_text(), re.M))))


def _table_names(text: str, header: str) -> set[str]:
    section = text.split(header, 1)[1].split("\n## ", 1)[0]
    return {name for cell in re.findall(r"^\| `([^|]+)` \|", section, re.M)
            for name in re.findall(r"[a-z_-]+", cell)}


def test_packaged_mirror_matches_skills() -> None:
    result = subprocess.run([sys.executable, str(ROOT / "tools/sync_harness_skills.py"), "--check"],
                            capture_output=True, text=True)
    assert result.returncode == 0, f"run python tools/sync_harness_skills.py\n{result.stdout}"


@pytest.mark.parametrize("stem", MCP_SKILL_STEMS)
def test_skill_frontmatter_is_valid_for_skill_hosts(stem: str) -> None:
    text = SKILLS[stem]
    assert text.startswith("---\n")
    assert re.search(rf"^name: {re.escape(stem)}$", text, re.M)
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", stem)
    assert 40 < len(skill_description(stem)) <= 1024


def test_every_query_is_documented_and_real() -> None:
    real = set(QueryProjectArgs.model_fields["query"].annotation.__args__)
    documented = _table_names(OPS, "## Queries")
    assert real == documented


def test_every_edit_operation_is_documented_and_real() -> None:
    real = set(pillar_tools._EDIT_ROUTING) | INLINE_OPS
    documented = _table_names(OPS, "## Edit operations")
    assert documented - real == set(), "skill names operations the server lacks"
    assert real - documented == set(), "server operations missing from open-edit-ops"


def test_every_generate_kind_is_documented() -> None:
    real = set(EditProjectArgs.model_fields["generate"].annotation.__args__[0].__args__)
    assert real <= _table_names(OPS, "## Generate")


def test_named_ir_methods_exist() -> None:
    named = set(re.findall(r"\bir\.([a-z_]+)\(", ALL_TEXT)) | set(
        re.findall(r"`([a-z_]+)`", OPS.split("`ir` methods", 1)[1].split("Captions,", 1)[0]))
    assert named, "expected run_script examples"
    assert {name for name in named if not hasattr(IR, name)} == set()


def test_every_catalog_effect_is_documented() -> None:
    effects = {p.stem for p in (ROOT / "open_edit/ir/catalog/effects").glob("*.yaml")} - {"dissolve"}
    assert {e for e in effects if f"`{e}`" not in SKILLS["open-edit-editing"]} == set()


@pytest.mark.parametrize("stale", [
    r"\binSec\b", r"\boutSec\b", r"\bsourceFile\b", r"TOOL_USAGE_GUIDE",
    r"\.py:\d+", r"from_clip_id", r"Prefer native HyperFrames", r"Run HyperFrames lint",
])
def test_known_stale_guidance_does_not_return(stale: str) -> None:
    hits = [stem for stem, text in SKILLS.items() if re.search(stale, text)]
    assert hits == [], f"{stale!r} reappeared in {hits}"


def test_token_budgets() -> None:
    assert len(mcp_instructions()) <= 900
    assert len(json.dumps(mcp_tool_schemas())) <= 9000
    assert len(SKILLS["open-edit"]) <= 5000
    assert sum(len(text) for text in SKILLS.values()) <= 30000


def test_legacy_skill_names_still_resolve() -> None:
    for old, new in LEGACY_STEMS.items():
        assert load_skill(old) == SKILLS[new]
    assert stem_from_uri("open-edit://skills/tool_surface") == "open-edit-ops"


def test_asset_manifest_is_valid_json() -> None:
    data = json.loads((ROOT / "open_edit/assets_manifest.json").read_text(encoding="utf-8"))
    assert data["assets"]
