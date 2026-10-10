"""Load harness-facing skill markdown for MCP and other agent hosts.

Canonical files live in the repo ``skills/<name>/SKILL.md`` layout (override
with ``OPEN_EDIT_SKILLS_DIR``). Packaged installs ship a mirror under
``open_edit/harness_skills/`` (``tools/sync_harness_skills.py`` writes it).
"""
from __future__ import annotations

import os
from functools import lru_cache
from importlib import resources
from pathlib import Path

# Stem → path relative to the skills directory.
SKILL_FILES: dict[str, str] = {
    "open-edit": "open-edit/SKILL.md",
    "open-edit-ops": "open-edit-ops/SKILL.md",
    "open-edit-editing": "open-edit-editing/SKILL.md",
    "open-edit-graphics": "open-edit-graphics/SKILL.md",
    "open-edit-review": "open-edit-review/SKILL.md",
    "README": "README.md",
}

# Exposed over MCP resources / prompts, entry skill first.
MCP_SKILL_STEMS: tuple[str, ...] = (
    "open-edit",
    "open-edit-ops",
    "open-edit-editing",
    "open-edit-graphics",
    "open-edit-review",
)

# Pre-1.4 flat skill names still resolve so saved prompts/URIs keep working.
LEGACY_STEMS: dict[str, str] = {
    "open-edit-mcp": "open-edit",
    "open-edit-mcp-reference": "open-edit-ops",
    "tool_surface": "open-edit-ops",
    "edit-planning": "open-edit-editing",
    "freeform_and_effects": "open-edit-editing",
    "qc-standards": "open-edit-editing",
    "hyperframes_native": "open-edit-graphics",
    "remotion_motion": "open-edit-graphics",
    "style-memory": "open-edit-review",
    "review-notes": "open-edit-review",
}

RESOURCE_URI_PREFIX = "open-edit://skills/"
_MARKER = SKILL_FILES["open-edit"]


def canonical_stem(stem: str) -> str | None:
    stem = LEGACY_STEMS.get(stem, stem)
    return stem if stem in SKILL_FILES else None


def skills_dir(env: dict[str, str] | None = None) -> Path | None:
    """Resolve the harness skills directory, or None if not found."""
    environ = env if env is not None else os.environ
    override = (environ.get("OPEN_EDIT_SKILLS_DIR") or "").strip()
    if override:
        path = Path(override).expanduser().resolve()
        return path if path.is_dir() else None

    # Walk up from this file looking for repo-root skills/open-edit/SKILL.md
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        candidate = parent / "skills"
        if (candidate / _MARKER).is_file():
            return candidate.resolve()

    # Packaged data: open_edit/harness_skills/ (ships with the wheel)
    packaged = Path(__file__).resolve().parent.parent / "harness_skills"
    if (packaged / _MARKER).is_file():
        return packaged

    try:
        root = resources.files("open_edit.harness_skills")
        if root.joinpath(_MARKER).is_file():
            return Path(str(root))
    except (TypeError, ModuleNotFoundError, AttributeError, OSError):
        pass

    return None


def skill_path(stem: str, env: dict[str, str] | None = None) -> Path | None:
    """Return path to a skill file by stem (legacy names accepted), or None."""
    canonical = canonical_stem(stem)
    root = skills_dir(env=env)
    if canonical is None or root is None:
        return None
    path = root / SKILL_FILES[canonical]
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


def skill_description(stem: str, env: dict[str, str] | None = None) -> str:
    """The frontmatter ``description`` (folded YAML ``>-`` supported), or ''."""
    try:
        text = load_skill(stem, env=env)
    except FileNotFoundError:
        return ""
    if not text.startswith("---\n"):
        return ""
    header = text[4:text.find("\n---", 4)]
    lines = header.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("description:"):
            value = line.split(":", 1)[1].strip()
            if value in (">-", ">", "|", "|-"):
                folded = []
                for follow in lines[index + 1:]:
                    if follow and not follow.startswith((" ", "\t")):
                        break
                    folded.append(follow.strip())
                value = " ".join(part for part in folded if part)
            return value
    return ""


def list_skill_stems(env: dict[str, str] | None = None) -> list[str]:
    """Stems present on disk (intersection with known SKILL_FILES)."""
    root = skills_dir(env=env)
    if root is None:
        return []
    return [stem for stem, filename in SKILL_FILES.items() if (root / filename).is_file()]


def resource_uri(stem: str) -> str:
    return f"{RESOURCE_URI_PREFIX}{stem}"


def stem_from_uri(uri: str) -> str | None:
    if not uri.startswith(RESOURCE_URI_PREFIX):
        return None
    return canonical_stem(uri[len(RESOURCE_URI_PREFIX):].strip("/"))


@lru_cache(maxsize=1)
def mcp_instructions() -> str:
    """Always-on startup context: kept small; details live in skill resources."""
    return (
        "Open Edit: edit video with query_project (reads), edit_project (writes), "
        "run_script (only when no operation fits), trigger_render (async; poll "
        "get_render_job), cancel_render_job. The project is pinned; never pass "
        "project_path. Don't read open_edit or node_modules source to learn APIs.\n"
        "Start: query_project get_readiness; on any missing_dependency error call it "
        "again and report its fix.\n"
        "Silence: generate=silence_cuts then apply_silence_gaps. Graphics: Diffusion "
        "first, HyperFrames for advanced HTML. Act on get_pending_notes before guessing.\n"
        f"Skills (load one when needed): {RESOURCE_URI_PREFIX}open-edit (playbook), "
        "open-edit-ops (exact params), open-edit-editing, open-edit-graphics, "
        "open-edit-review. Also MCP prompts of the same names.\n"
    )
