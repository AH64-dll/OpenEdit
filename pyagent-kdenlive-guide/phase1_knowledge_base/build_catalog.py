#!/usr/bin/env python3
"""
build_catalog.py — Phase 1, task 1+2.

Ingests the four local data sources and produces a single normalized JSON
catalog PyAgent's system prompt / tool definitions can be built from.

Sources (all local on this machine; see spike-results/versions.txt):
  1. /usr/share/kdenlive/effects/*.xml         (386 effect definitions)
  2. /usr/share/kdenlive/transitions/*.xml     ( 58 transition definitions)
  3. /usr/share/kdenlive/generators/*.xml      (  3 generator definitions)
  4. /usr/share/kdenlive/kdenliveeffectscategory.rc
     (groups effects by category — used to attach `category` to each entry)
  5. /usr/share/mlt-7/**/*.yml                 (186 MLT service metadata files)

Output: catalog.json next to this script.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

# The Kdenlive schema uses two different namespace conventions in the wild:
#   - <effect xmlns="https://www.kdenlive.org" ...>  (e.g. effect/avfilter files)
#   - <transition ...>                              (no xmlns, default ns; older files)
# We support both. We sniff the root tag's local name and look up children
# under whichever prefix they actually use.
KDE_NS = "https://www.kdenlive.org"
KDE = f"{{{KDE_NS}}}"


def _ns(root: ET.Element) -> str:
    """Return the namespace prefix actually used by the root's children."""
    # Walk one level of children to discover the prefix in use.
    for child in root:
        tag = child.tag
        if tag.startswith("{"):
            return tag[: tag.find("}") + 1]
    return ""


def _t(root: ET.Element, local: str, ns: str) -> ET.Element | None:
    return root.find(f"{ns}{local}") if ns else root.find(local)

KDENLIVE_DATA = Path("/usr/share/kdenlive")
MLT_DATA = Path("/usr/share/mlt-7")

OUT_PATH = Path(__file__).parent / "catalog.json"


def parse_param(param: ET.Element, ns: str = "") -> dict:
    """Extract a single <parameter> into a flat dict.

    Kept for backwards-compat / one-off use; the main path calls
    _parse_param directly.
    """
    p = {
        "name": param.get("name"),
        "type": param.get("type"),
    }
    for k in (
        "min",
        "max",
        "default",
        "factor",
        "suffix",
        "paramlist",
        "paramlistdisplay",
        "filter",
        "newstuff",
        "optional",
        "value",
        "rows",
    ):
        v = param.get(k)
        if v is not None:
            p[k] = v
    name_el = _t(param, "name", ns) if ns else param.find("name")
    if name_el is not None and name_el.text:
        p["display_name"] = name_el.text.strip()
    desc_el = _t(param, "description", ns) if ns else param.find("description")
    if desc_el is not None and desc_el.text:
        p["description"] = desc_el.text.strip()
    return p


def parse_effect_xml(path: Path) -> dict | None:
    """Parse a Kdenlive effects/transitions/generators XML file."""
    try:
        tree = ET.parse(path)
    except ET.ParseError as e:
        print(f"  parse error in {path}: {e}", file=sys.stderr)
        return None
    root = tree.getroot()
    kind = root.tag.split("}", 1)[1] if root.tag.startswith("{") else root.tag
    if kind not in ("effect", "transition", "generator"):
        return None
    ns = _ns(root)  # "" for default-ns files, "{}", for namespaced ones
    entry: dict = {
        "kind": kind,
        "kdenlive_id": root.get("id") or root.get("tag"),
        "mlt_service": root.get("tag"),
        "source": str(path),
    }
    if root.get("type"):
        entry["kdenlive_type"] = root.get("type")  # e.g. "videotransition"
    for local, key in (
        ("name", "name"),
        ("description", "description"),
        ("author", "author"),
        ("version", "version"),
    ):
        el = _t(root, local, ns)
        if el is not None and el.text:
            entry[key] = el.text.strip()
    params = list(root)  # children of root
    param_local = f"{ns}parameter" if ns else "parameter"
    params = [c for c in params if c.tag == param_local]
    if params:
        # Each <parameter> child also uses the parent's namespace prefix.
        for p in params:
            p.tag = p.tag  # no-op; just for clarity
        entry["parameters"] = [_parse_param(p, ns) for p in params]
    return entry


def _parse_param(param: ET.Element, ns: str) -> dict:
    """Extract a single <parameter> into a flat dict."""
    p = {
        "name": param.get("name"),
        "type": param.get("type"),
    }
    for k in (
        "min",
        "max",
        "default",
        "factor",
        "suffix",
        "paramlist",
        "paramlistdisplay",
        "filter",
        "newstuff",
        "optional",
        "value",
        "rows",
    ):
        v = param.get(k)
        if v is not None:
            p[k] = v
    name_el = _t(param, "name", ns)
    if name_el is not None and name_el.text:
        p["display_name"] = name_el.text.strip()
    desc_el = _t(param, "description", ns)
    if desc_el is not None and desc_el.text:
        p["description"] = desc_el.text.strip()
    return p


def load_kdenlive_category_index() -> dict[str, str]:
    """kdenliveeffectscategory.rc groups effects by category text."""
    rc_path = KDENLIVE_DATA / "kdenliveeffectscategory.rc"
    if not rc_path.exists():
        return {}
    text = rc_path.read_text(encoding="utf-8")
    out: dict[str, str] = {}
    for m in re.finditer(
        r'<group\s+list="([^"]+)"[^>]*>\s*<text>([^<]+)</text>', text
    ):
        ids_csv, category = m.group(1), m.group(2).strip()
        for kid in ids_csv.split(","):
            kid = kid.strip()
            if kid:
                out[kid] = category
    return out


def parse_mlt_yaml(path: Path) -> dict | None:
    """Very small YAML reader for MLT service metadata.

    We don't need PyYAML for the fields PyAgent cares about — the schema
    is flat-ish and lines are predictable. Falls back to None if the
    format is too complex.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if not raw.startswith("schema_version:"):
        return None
    out: dict = {"source": str(path)}

    # Helper for a top-level scalar.
    for key in ("schema_version", "type", "identifier", "title", "version", "description"):
        m = re.search(rf"^{re.escape(key)}:\s*(.+?)\s*$", raw, re.MULTILINE)
        if m:
            v = m.group(1).strip().strip("'\"")
            if v and v != "~":
                out[key] = v
    return out or None


def main() -> int:
    catalog: dict = {
        "schema_version": 1,
        "source_machine": "arch-linux",
        "kdenlive_data_dir": str(KDENLIVE_DATA),
        "mlt_data_dir": str(MLT_DATA),
        "effects": [],
        "transitions": [],
        "generators": [],
        "mlt_services": [],
        "category_index": load_kdenlive_category_index(),
    }

    print("Parsing Kdenlive effect XMLs...", file=sys.stderr)
    for p in sorted((KDENLIVE_DATA / "effects").glob("*.xml")):
        entry = parse_effect_xml(p)
        if entry is None:
            continue
        cat = catalog["category_index"].get(entry.get("kdenlive_id") or "")
        if cat:
            entry["category"] = cat
        catalog["effects"].append(entry)
    print(f"  {len(catalog['effects'])} effects", file=sys.stderr)

    print("Parsing Kdenlive transition XMLs...", file=sys.stderr)
    for p in sorted((KDENLIVE_DATA / "transitions").glob("*.xml")):
        entry = parse_effect_xml(p)
        if entry is None:
            continue
        catalog["transitions"].append(entry)
    print(f"  {len(catalog['transitions'])} transitions", file=sys.stderr)

    print("Parsing Kdenlive generator XMLs...", file=sys.stderr)
    gen_dir = KDENLIVE_DATA / "generators"
    if gen_dir.exists():
        for p in sorted(gen_dir.glob("*.xml")):
            entry = parse_effect_xml(p)
            if entry is None:
                continue
            catalog["generators"].append(entry)
    print(f"  {len(catalog['generators'])} generators", file=sys.stderr)

    print("Indexing MLT YAML service metadata...", file=sys.stderr)
    n_total = 0
    n_parsed = 0
    for p in sorted(MLT_DATA.rglob("*.yml")):
        n_total += 1
        entry = parse_mlt_yaml(p)
        if entry is None:
            continue
        n_parsed += 1
        # Tag with the module subdir (e.g. "oldfilm", "kdenlive", "plus").
        rel = p.relative_to(MLT_DATA)
        if len(rel.parts) > 1:
            entry["mlt_module"] = rel.parts[0]
        catalog["mlt_services"].append(entry)
    print(f"  {n_parsed}/{n_total} MLT YAMLs parsed", file=sys.stderr)

    # Cross-reference: every kdenlive effect's mlt_service -> MLT entry
    # (best-effort, by `identifier`).
    by_id = {e.get("identifier"): e for e in catalog["mlt_services"] if e.get("identifier")}
    for e in catalog["effects"] + catalog["transitions"] + catalog["generators"]:
        svc = e.get("mlt_service")
        if svc and svc in by_id:
            mlt = by_id[svc]
            e["mlt_metadata"] = {
                "title": mlt.get("title"),
                "type": mlt.get("type"),
                "description": mlt.get("description"),
                "source": mlt.get("source"),
            }

    OUT_PATH.write_text(json.dumps(catalog, indent=2, sort_keys=False))
    print(f"Wrote {OUT_PATH}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
