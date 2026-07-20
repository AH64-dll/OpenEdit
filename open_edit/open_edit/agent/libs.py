"""Parse `# ir_api_version: X.Y; libs: {...}` headers and check against the
allowed manifest.

H6: SandboxError imported.
H8: header requires quoted dict keys (Python literal syntax).
L8: manifest is TOML (Python 3.11+ tomllib stdlib).
"""
from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path

from open_edit.agent.exceptions import SandboxError

_HEADER_RE = re.compile(
    r'^\s*#\s*ir_api_version:\s*(\S+)\s*;\s*libs:\s*(\{.*?\})\s*$',
    re.MULTILINE,
)

ALLOWED_LIBS_PATH = Path(__file__).parent / "allowed_libs.toml"


def parse_header(code: str) -> tuple[str, dict[str, str]]:
    """Parse the ir_api_version header from a free-form Python script.

    Returns (version, libs_dict). libs_dict is {lib_name: version_str}.

    Raises SandboxError on missing/malformed header or unparseable libs.
    """
    m = _HEADER_RE.search(code)
    if not m:
        raise SandboxError(
            "missing or malformed ir_api_version header "
            "(expected: # ir_api_version: X.Y; libs: {\"name\": \"ver\"})"
        )
    version = m.group(1)
    try:
        libs = ast.literal_eval(m.group(2))
    except (ValueError, SyntaxError) as e:
        raise SandboxError(f"libs dict is not valid Python: {e}") from e
    if not isinstance(libs, dict):
        raise SandboxError(f"libs must be a dict, got {type(libs).__name__}")
    for k, v in libs.items():
        if not isinstance(k, str) or not isinstance(v, str):
            raise SandboxError(f"libs keys/values must be strings: {libs!r}")
    return version, libs


def version_supported(declared: str) -> bool:
    manifest = _load_manifest()
    return declared in manifest.get("ir_api_versions", [])


def lib_version_supported(name: str, ver: str) -> bool:
    manifest = _load_manifest()
    return ver in manifest.get("libs", {}).get(name, {}).get("versions", [])


def _load_manifest() -> dict:
    with open(ALLOWED_LIBS_PATH, "rb") as f:
        return tomllib.load(f)
