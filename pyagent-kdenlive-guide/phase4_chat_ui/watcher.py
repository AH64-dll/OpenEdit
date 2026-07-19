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
    mtime_window_sec: float = 1.0,
) -> None:
    """Watch `project` and call `on_change(project)` whenever it is modified.

    Runs until cancelled. `poll_delay_ms` is the watchfiles poll interval.
    `mtime_window_sec` is the maximum allowed gap between a changed file's
    mtime and the project's mtime; events outside the window are ignored,
    which suppresses false positives from unrelated sibling-file writes
    (e.g., a thumbnail regenerating, an autosave in another tool).
    """
    project_path = Path(project)
    watch_dir = str(project_path.parent)
    target_name = project_path.name

    last_project_mtime: float | None = None
    async for changes in awatch(
        watch_dir, step=int(poll_delay_ms), poll_delay_ms=poll_delay_ms
    ):
        try:
            project_mtime = project_path.stat().st_mtime
        except OSError:
            await on_change(project)
            last_project_mtime = None
            continue

        # Path 1: project's own mtime moved since our last poll — this is
        # the atomic-rename case (os.replace of a sibling onto the project).
        if last_project_mtime is not None and abs(project_mtime - last_project_mtime) > 0.001:
            await on_change(project)
            last_project_mtime = project_mtime
            continue

        # Path 2: a file-level change in the directory matches the project
        # file's name, and its mtime is within the window of the project's.
        for c in changes:
            changed_path = c[1] if isinstance(c, tuple) else c
            changed_str = str(changed_path)
            if changed_str == watch_dir:
                continue  # dir-level event; no file mtime to compare
            if Path(changed_str).name != target_name:
                continue
            try:
                changed_mtime = Path(changed_path).stat().st_mtime
            except OSError:
                # File gone — atomic rename just completed. Trust the dir
                # event from watchfiles and fire.
                await on_change(project)
                break
            if abs(changed_mtime - project_mtime) <= mtime_window_sec:
                await on_change(project)
                break

        last_project_mtime = project_mtime
