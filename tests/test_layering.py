"""Layering guard tests.

Enforce the hard dependency rules:
- kernel must never import ``open_edit.serve`` (serve is the outermost layer)
- ir must stay pure: never import agent / storage / serve / kernel
- storage must not import below its boundary: ``ir.apply`` / ``ir.api`` / ``ir.factory``
  (``ir.ids`` / ``ir.hash`` / ``ir.types`` / ``ir.validate`` / ``ir.derive`` are permitted)
- mcp must never import ``open_edit.serve``

Guards match actual ``import``/``from`` statements only (dotted-path components),
so comments or docstrings mentioning a banned module cannot false-positive.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "open_edit"

_IMPORT_LINE = re.compile(r"^\s*(?P<kind>from|import)\s+(?P<rest>.+?)\s*$", re.MULTILINE)


def _py_files(pkg: str) -> list[Path]:
    return list((SRC / pkg).rglob("*.py"))


def _imports_module(src: str, module: str) -> bool:
    """True if src contains an import statement for ``module`` (exact dotted-path component)."""
    target = module.split(".")
    for m in _IMPORT_LINE.finditer(src):
        kind, rest = m.group("kind"), m.group("rest")
        if kind == "from":
            names = [rest.split(" import ", 1)[0].strip()]
        else:
            names = [name.split(" as ")[0].strip() for name in rest.split(",")]
        for name in names:
            parts = name.split(".")
            if parts == target or parts[: len(target)] == target or parts[-len(target):] == target:
                return True
    return False


def _offenders(pkg: str, banned: list[str]) -> list[str]:
    out = []
    for path in _py_files(pkg):
        src = path.read_text(encoding="utf-8")
        for module in banned:
            if _imports_module(src, module):
                out.append(f"{path.relative_to(SRC)}: {module}")
    return out


def test_kernel_never_imports_serve():
    assert _offenders("kernel", ["open_edit.serve"]) == []


def test_ir_never_imports_upper_layers():
    assert _offenders(
        "ir",
        ["open_edit.agent", "open_edit.storage", "open_edit.serve", "open_edit.kernel"],
    ) == []


def test_storage_never_imports_apply_or_api():
    assert _offenders("storage", ["ir.apply", "ir.api", "ir.factory"]) == []


def test_mcp_never_imports_serve():
    assert _offenders("mcp", ["open_edit.serve"]) == []
