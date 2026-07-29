"""Compatibility shim — tool execution lives in ``open_edit.kernel.tool_executor``."""
from open_edit.kernel.tool_executor import (
    ToolNotFound,
    execute_tool,
    execute_trigger_render,
)

__all__ = ["ToolNotFound", "execute_tool", "execute_trigger_render"]
