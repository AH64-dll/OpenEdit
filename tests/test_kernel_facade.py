import subprocess
import sys
from pathlib import Path

import open_edit.kernel as kernel

RE_EXPORTED = [
    "DEFAULT_RENDER_JOB_SERVICE",
    "RenderEnqueueError",
    "RenderJobService",
    "EditGraphCommandError",
    "apply_command",
    "build_tool_schemas",
    "dispatch_edit",
    "dispatch_generate",
    "dispatch_query",
    "execute_tool",
    "execute_trigger_render",
    "validate_or_error",
    "TOOL_SCHEMAS",
]


def test_kernel_facade_exports():
    for name in kernel.__all__:
        assert getattr(kernel, name) is not None, name
    assert set(kernel.__all__) == set(RE_EXPORTED)


def test_kernel_does_not_import_serve():
    root = str(Path(__file__).resolve().parent.parent)
    code = (
        "import open_edit.kernel, sys; "
        "assert not any(m.startswith('open_edit.serve') for m in sys.modules), "
        "[m for m in sys.modules if m.startswith('open_edit.serve')]"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=root,
    )
    assert result.returncode == 0, result.stderr
