"""Phase 3 Task 3: parse_header + version_supported + lib_version_supported."""
import textwrap
from pathlib import Path

import pytest

from open_edit.agent.exceptions import SandboxError
from open_edit.agent.libs import (
    ALLOWED_LIBS_PATH,
    lib_version_supported,
    parse_header,
    version_supported,
)


def test_parse_header_minimal():
    code = "# ir_api_version: 0.1; libs: {}"
    v, libs = parse_header(code)
    assert v == "0.1"
    assert libs == {}


def test_parse_header_with_libs():
    code = '# ir_api_version: 0.1; libs: {"numpy": "1.26.4"}'
    v, libs = parse_header(code)
    assert v == "0.1"
    assert libs == {"numpy": "1.26.4"}


def test_parse_header_missing_raises():
    code = "import os  # no header"
    with pytest.raises(SandboxError, match="missing or malformed"):
        parse_header(code)


def test_parse_header_unquoted_keys_raises():
    """H8: ast.literal_eval rejects unquoted dict keys."""
    code = "# ir_api_version: 0.1; libs: {numpy: 1.26.4}"
    with pytest.raises(SandboxError, match="not valid Python"):
        parse_header(code)


def test_version_supported_true():
    assert version_supported("0.1") is True


def test_version_supported_false():
    assert version_supported("99.0") is False


def test_lib_version_supported_true():
    assert lib_version_supported("numpy", "1.26.4") is True


def test_lib_version_supported_false():
    assert lib_version_supported("numpy", "99.0") is False
    assert lib_version_supported("nonexistent", "1.0") is False


def test_allowed_libs_path_is_toml():
    assert ALLOWED_LIBS_PATH.suffix == ".toml"
    assert ALLOWED_LIBS_PATH.exists()
