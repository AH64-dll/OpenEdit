"""Cost sidecar persistence (v1.4 P1-3).

The cumulative session cost is persisted as a sidecar JSON file
at ``<project>/.open_edit/cost.json``, keyed by ``conv_id``. The
sidecar is small (one float per conversation) and lazy: we read
it at turn start and write it via ``asyncio.to_thread`` so the
disk I/O doesn't block the WS event loop. A separate SQLite
table alongside ``edit_graph.db`` was an option, but the
sidecar keeps ``EditGraphStore``'s schema untouched and keeps
cost data trivially inspectable from the command line.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

# Source-priority for the cost_update event. When a turn has
# multiple LLM calls with different ``usage.source`` values (e.g.
# a partial provider switch, or a pi call followed by a
# misconfigured anthropic call), we report the highest-priority
# non-"unavailable" source on the cost_update so the UI can show
# the most informative label. Pi is preferred because the user's
# default is pi and pi's numbers are authoritative for that path.
_SOURCE_PRIORITY = {"pi": 0, "computed": 1, "unavailable": 2}


def _cost_sidecar_path(project_path: Path) -> Path:
    """Path of the per-project cost sidecar JSON."""
    return project_path / ".open_edit" / "cost.json"


def _load_cost_state(project_path: Path) -> dict[str, dict[str, Any]]:
    """Read the cost sidecar for a project.

    Returns a flat dict ``{conv_id: {session_cost_usd, source, last_turn_cost_usd}}``.
    Missing/corrupt files return ``{}`` — we never raise on read
    so a malformed sidecar can't crash the agent loop. The
    operator can ``rm .open_edit/cost.json`` to reset.
    """
    p = _cost_sidecar_path(project_path)
    if not p.exists():
        return {}
    try:
        with p.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _write_cost_json_sync(path: Path, state: dict[str, dict[str, Any]]) -> None:
    """Synchronous JSON write — wrapped in ``asyncio.to_thread`` by
    callers so disk I/O doesn't block the event loop. Atomic via
    temp file + ``os.replace`` so a crash mid-write can't leave
    the sidecar in a half-written state."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(state, fh, sort_keys=True, default=str)
    os.replace(tmp, path)


def _save_cost_state(
    project_path: Path, state: dict[str, dict[str, Any]],
) -> None:
    """Synchronous save — tests use this; the agent loop uses
    ``_save_cost_state_async`` for off-loop writes.

    Merges with the existing sidecar so unrelated conv_ids (other
    conversations in the same project) are preserved. The merge
    is in-memory + atomic write: load the existing file, update
    the entries from ``state``, write back. A sidecar with N
    conversations is small (a few KB at most) so re-reading it
    on every save is fine.
    """
    existing = _load_cost_state(project_path)
    existing.update(state)
    _write_cost_json_sync(_cost_sidecar_path(project_path), existing)


# Keep a strong reference to background tasks so they are not garbage-collected
# before the event loop schedules them (CPython can collect unreferenced tasks
# on 3.10+). The done-callback drops the reference once the task finishes.
_BG_TASKS: set[asyncio.Task] = set()


def _create_bg_task(coro: Any) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _BG_TASKS.add(task)
    task.add_done_callback(_BG_TASKS.discard)
    return task


async def _save_cost_state_async(
    project_path: Path, state: dict[str, dict[str, Any]],
) -> None:
    """Async save — runs the disk I/O on a thread so the WS loop
    stays responsive. The brief says cost persistence is
    'lazy-loaded; don't block turn completion on disk I/O'; this
    is that."""
    await asyncio.to_thread(
        _write_cost_json_sync, _cost_sidecar_path(project_path), state,
    )


# ---------------------------------------------------------------------------
# Turn-level cost aggregation (single path for SDK and CLI-owned loops)
# ---------------------------------------------------------------------------

def accumulate_usage(event: dict[str, Any], state: dict[str, Any]) -> None:
    """Merge one ``usage`` StreamEvent into the per-turn accumulation
    ``state`` dict.

    The state dict carries ``turn_tokens``, ``turn_cost_usd``,
    ``best_source_priority`` and ``best_source``. The source-priority
    ranking lives here (not in the loops) so the SDK loop and the
    CLI-owned loop cannot drift on which source wins a mixed turn.
    """
    try:
        state["turn_tokens"] += int(event.get("tokens", 0) or 0)
        state["turn_cost_usd"] += float(event.get("cost_usd", 0.0) or 0.0)
    except (TypeError, ValueError):
        pass
    src = event.get("source", "unavailable")
    if not isinstance(src, str):
        src = "unavailable"
    prio = _SOURCE_PRIORITY.get(src, _SOURCE_PRIORITY["unavailable"])
    if prio < state["best_source_priority"]:
        state["best_source_priority"] = prio
        state["best_source"] = src


def emit_cost_update(state: dict[str, Any]) -> dict[str, Any]:
    """Build the terminal ``cost_update`` event for a turn and persist
    the new session cumulative to the sidecar.

    The state dict carries ``previous_session_cost``, ``turn_tokens``,
    ``turn_cost_usd`` and ``best_source`` (from ``accumulate_usage``),
    plus ``cost_state``, ``project_path`` and ``conv_id`` for the
    persistence. Call sites yield the returned event after ``done``;
    the sidecar write is fire-and-forget via ``_save_cost_state_async``
    so turn completion never blocks on disk I/O.
    """
    session_cost_usd = state["previous_session_cost"] + state["turn_cost_usd"]
    event = {
        "type": "cost_update",
        "turn_tokens": state["turn_tokens"],
        "turn_cost_usd": round(state["turn_cost_usd"], 9),
        "session_cost_usd": round(session_cost_usd, 9),
        "source": state["best_source"],
    }
    conv_id = state.get("conv_id")
    if conv_id:
        state["cost_state"][conv_id] = {
            "session_cost_usd": session_cost_usd,
            "source": state["best_source"],
            "last_turn_cost_usd": state["turn_cost_usd"],
        }
        _create_bg_task(
            _save_cost_state_async(state["project_path"], dict(state["cost_state"]))
        )
    return event
