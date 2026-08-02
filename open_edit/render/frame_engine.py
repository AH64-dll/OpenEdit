"""Host-only frame-engine contracts consumed by preview chunk rendering."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol, TypedDict, runtime_checkable

from open_edit.ir.types import Timeline
from open_edit.render.profiles import RenderProfile


class PreviewVideoRequest(TypedDict):
    """One frame-aligned preview range and its rendering context."""

    project_dir: Path
    timeline: Timeline
    render_start_frame: int
    render_end_frame: int
    core_start_frame: int
    core_end_frame: int
    composition_uids: tuple[str, ...]
    profile: RenderProfile
    output_path: Path


@runtime_checkable
class PreviewVideoRenderer(Protocol):
    """Render one preview range and return its validated video artifact."""

    def render(self, request: PreviewVideoRequest) -> Path:
        """Render one range and return the validated video artifact path."""


__all__ = ["PreviewVideoRenderer", "PreviewVideoRequest"]
