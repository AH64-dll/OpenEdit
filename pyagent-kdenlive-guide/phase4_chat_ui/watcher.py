"""File watcher — notifies the app when the project file changes on disk.

This is the Phase 5 handoff hook: any write to the .kdenlive file (whether by
PyAgent or an external editor / Kdenlive) triggers `on_change` so the UI can
refresh project state at the right moment — after the write completes, not
before.

Uses watchfiles' async watcher, which is efficient and cross-platform.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

from watchfiles import awatch

ChangeHandler = Callable[[str], Awaitable[None]]


async def watch_project(
    project: str,
    on_change: ChangeHandler,
    poll_delay_ms: int = 200,
) -> None:
    """Watch `project` and call `on_change(project)` whenever it is modified.

    Runs until cancelled. `poll_delay_ms` is the watchfiles poll interval.
    """
    path = Path(project)
    watch_dir = str(path.parent)
    target_name = path.name
    async for _changes in awatch(watch_dir, step=int(poll_delay_ms), poll_delay_ms=poll_delay_ms):
        # Only react to changes touching the project file itself.
        if any(target_name in (c[1] if isinstance(c, tuple) else str(c)) for c in _changes):
            await on_change(project)
