"""Build the filtered catalog slice used in the system prompt.

The slice is one line per catalog entry:
    {tag} | {kdenlive_id} | {name} | {description}

Entries without a `name` are excluded. Only `effects`, `transitions`, and
`generators` kinds are included; metadata fields are ignored.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


DEFAULT_KINDS: tuple[str, ...] = ("effects", "transitions", "generators")


def build_catalog_slice(
    catalog: dict | str | Path,
    kinds: Iterable[str] = DEFAULT_KINDS,
) -> str:
    """Return the catalog slice as a multi-line string.

    Args:
        catalog: a dict (the parsed catalog.json contents) or a path to the
                 JSON file.
        kinds: which top-level keys to include. Default: all three.

    Returns:
        A newline-separated string, one line per entry. Empty string if no
        named entries match.
    """
    if isinstance(catalog, (str, Path)):
        catalog = json.loads(Path(catalog).read_text())

    lines: list[str] = []
    for kind in kinds:
        for entry in catalog.get(kind, []):
            name = entry.get("name")
            if not name:
                continue  # skip unnamed entries
            tag = entry.get("tag", "")
            entry_id = entry.get("id", "")
            description = (entry.get("description", "") or "").strip()
            lines.append(f"{tag} | {entry_id} | {name} | {description}")
    return "\n".join(lines)
