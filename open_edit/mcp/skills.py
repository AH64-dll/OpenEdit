"""Load harness-facing skill markdown for MCP and other agent hosts.

Canonical files live in the repo ``skills/`` directory (override with
``OPEN_EDIT_SKILLS_DIR``). Packaged installs may also ship copies under
``open_edit/harness_skills/``.
"""
from __future__ import annotations

import os
from functools import lru_cache
from importlib import resources
from pathlib import Path

# Stem → filename (without path)
SKILL_FILES: dict[str, str] = {
    "open-edit-mcp": "open-edit-mcp.md",
    "open-edit-mcp-reference": "open-edit-mcp-reference.md",
    "tool_surface": "tool_surface.md",
    "edit-planning": "edit-planning.md",
    "remotion_motion": "remotion_motion.md",
    "qc-standards": "qc-standards.md",
    "freeform_and_effects": "freeform_and_effects.md",
    "README": "README.md",
}

# Exposed over MCP resources / prompts (keep the set small for hosts).
MCP_SKILL_STEMS: tuple[str, ...] = (
    "open-edit-mcp",
    "open-edit-mcp-reference",
    "tool_surface",
    "edit-planning",
    "remotion_motion",
)

RESOURCE_URI_PREFIX = "open-edit://skills/"


def skills_dir(env: dict[str, str] | None = None) -> Path | None:
    """Resolve the harness skills directory, or None if not found."""
    environ = env if env is not None else os.environ
    override = (environ.get("OPEN_EDIT_SKILLS_DIR") or "").strip()
    if override:
        path = Path(override).expanduser().resolve()
        return path if path.is_dir() else None

    # Walk up from this file looking for repo-root skills/open-edit-mcp.md
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        candidate = parent / "skills"
        if (candidate / "open-edit-mcp.md").is_file():
            return candidate.resolve()
        # open_edit/ package sibling: .../open_edit/../skills
        sibling = parent.parent / "skills"
        if (sibling / "open-edit-mcp.md").is_file():
            return sibling.resolve()

    # Packaged data: open_edit/harness_skills/ (ships with the wheel)
    packaged = Path(__file__).resolve().parent.parent / "harness_skills"
    if (packaged / "open-edit-mcp.md").is_file():
        return packaged

    try:
        root = resources.files("open_edit.harness_skills")
        marker = root.joinpath("open-edit-mcp.md")
        if marker.is_file():
            return Path(str(root))
    except (TypeError, ModuleNotFoundError, AttributeError, OSError):
        pass

    return None


def skill_path(stem: str, env: dict[str, str] | None = None) -> Path | None:
    """Return path to a skill file by stem, or None."""
    filename = SKILL_FILES.get(stem)
    if not filename:
        return None
    root = skills_dir(env=env)
    if root is None:
        return None
    path = root / filename
    return path if path.is_file() else None


def load_skill(stem: str, env: dict[str, str] | None = None) -> str:
    """Load skill markdown by stem. Raises FileNotFoundError if missing."""
    path = skill_path(stem, env=env)
    if path is None:
        raise FileNotFoundError(
            f"harness skill {stem!r} not found "
            f"(set OPEN_EDIT_SKILLS_DIR or install package skills)"
        )
    return path.read_text(encoding="utf-8")


def list_skill_stems(env: dict[str, str] | None = None) -> list[str]:
    """Stems present on disk (intersection with known SKILL_FILES)."""
    root = skills_dir(env=env)
    if root is None:
        return []
    found: list[str] = []
    for stem, filename in SKILL_FILES.items():
        if (root / filename).is_file():
            found.append(stem)
    return found


def resource_uri(stem: str) -> str:
    return f"{RESOURCE_URI_PREFIX}{stem}"


def stem_from_uri(uri: str) -> str | None:
    if not uri.startswith(RESOURCE_URI_PREFIX):
        return None
    stem = uri[len(RESOURCE_URI_PREFIX) :].strip("/")
    return stem if stem in SKILL_FILES else None


@lru_cache(maxsize=1)
def mcp_instructions() -> str:
    """Short instructions injected on MCP initialize for any harness."""
    try:
        body = load_skill("open-edit-mcp")
    except FileNotFoundError:
        return _FALLBACK_INSTRUCTIONS
    # Drop YAML frontmatter if present to keep initialize payload lean-ish
    if body.startswith("---"):
        end = body.find("\n---", 3)
        if end != -1:
            body = body[end + 4 :].lstrip("\n")
    return (
        "Open Edit MCP agent playbook (follow this; do not explore source "
        "to rediscover tools):\n\n"
        + body
    )


_FALLBACK_INSTRUCTIONS = """\
Open Edit MCP tools: query_project, edit_project, run_script, trigger_render,
get_render_job, cancel_render_job. Prefer tools over exploring source.
Priority: query → edit → run_script (only if needed) → trigger_render (proxy then final).
Silence: edit_project generate=silence_cuts — never ffmpeg silencedetect.
Ingest: edit_project operation=ingest_local with absolute paths.
Project path is pinned at server start; never pass project_path as an argument.
"""
