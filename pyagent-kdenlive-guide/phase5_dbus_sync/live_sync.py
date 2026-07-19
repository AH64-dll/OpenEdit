"""LiveSync: routes mutating ops to D-Bus (live) or file backend (reload).

The D-Bus live methods on the Kdenlive 26.04 build we target
(addTimelineClip / addProjectClip / cleanRestart) are UNSTABLE and
crash the running instance, so LIVE_CAPABLE is intentionally empty:
all mutating ops go through the Phase 3 file backend, after quitting
Kdenlive (so it can't overwrite our edits on save/close) and notifying
the user to reload.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

# Make Phase 3 importable (it lives in a sibling package at repo root).
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from phase3_pyagent_core.__main__ import run_op  # noqa: E402

from phase5_dbus_sync.dbus_client import (  # noqa: E402
    KdenliveDBus, detect_service_name,
)


# On Kdenlive 26.04, every D-Bus live method crashes the running
# instance. All mutating ops go through the file backend instead.
LIVE_CAPABLE: frozenset[str] = frozenset()

# Tools whose file-mode write needs a "reload to see changes" notice.
RELOAD_AFTER: frozenset[str] = frozenset({
    "pyagent_import_media", "pyagent_insert_clip", "pyagent_append_clip",
    "pyagent_move_clip", "pyagent_trim_clip", "pyagent_delete_clip",
    "pyagent_add_transition", "pyagent_apply_effect", "pyagent_add_marker",
    "pyagent_save_project",
})

# pi tool name -> phase3 backend op name.
_OP_FOR_TOOL = {
    "pyagent_import_media": "import_media",
    "pyagent_insert_clip": "insert_clip",
    "pyagent_append_clip": "append_clip",
    "pyagent_move_clip": "move_clip",
    "pyagent_trim_clip": "trim_clip",
    "pyagent_delete_clip": "delete_clip",
    "pyagent_add_transition": "add_transition",
    "pyagent_apply_effect": "apply_effect",
    "pyagent_add_marker": "add_marker",
    "pyagent_save_project": "save",
}


def notify(title: str, body: str) -> None:
    """Shell out to `notify-send`. Returns silently if not available."""
    if shutil.which("notify-send") is None:
        return
    try:
        subprocess.run(
            ["notify-send", "--urgency=normal", title, body],
            check=False, timeout=5,
        )
    except Exception:
        pass


@dataclass
class LiveResult:
    """Result of a LiveSync.apply() call. JSON-serializable via asdict()."""
    ok: bool
    mode: str  # "live" or "file"
    result: dict = field(default_factory=dict)
    fatal: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def apply(tool: str, args: dict, project: str,
          notifier: Callable[[str, str], None] = notify) -> dict:
    """Module-level entry point. Routes `tool` through the appropriate
    backend for `project` (a .kdenlive file path)."""
    return LiveSync(project, notifier=notifier).apply(tool, args).to_dict()


class LiveSync:
    def __init__(self, project_path: str,
                 dbus: KdenliveDBus | None = None,
                 notifier: Callable[[str, str], None] = notify) -> None:
        self.project_path = project_path
        self._notifier = notifier
        service = detect_service_name()
        self._dbus = dbus or (KdenliveDBus(service) if service else None)
        self._catalog = str(_REPO_ROOT / "phase1_knowledge_base" / "catalog.json")

    def is_live(self, tool: str) -> bool:
        return (tool in LIVE_CAPABLE
                and self._dbus is not None and self._dbus.available)

    def apply(self, tool: str, args: dict) -> LiveResult:
        # Live D-Bus path: if it succeeds, Kdenlive is in sync and we
        # must NOT quit it (that would defeat the purpose of live edit).
        if self.is_live(tool) and self._apply_via_dbus(tool, args):
            return LiveResult(ok=True, mode="live", result={"mode": "live"})
        # File fallback: Kdenlive keeps the project in memory and would
        # overwrite our edits. Quit it first so our file is authoritative.
        self._quit_kdenlive_if_running()
        result = self._apply_via_file(tool, args)
        if result.ok and tool in RELOAD_AFTER:
            self._notify_reload_needed()
        return result

    def _apply_via_dbus(self, tool: str, args: dict) -> bool:
        assert self._dbus is not None
        if tool == "pyagent_import_media":
            paths = args.get("paths") or []
            url = paths[0] if paths else args.get("path", "")
            return bool(url) and self._dbus.add_project_clip(str(url))
        if tool == "pyagent_append_clip":
            url = self._source_id_to_url(args.get("source_id", ""))
            return self._dbus.add_timeline_clip(url) if url else False
        if tool == "pyagent_apply_effect":
            return self._dbus.add_effect(str(args.get("effect_id", "")))
        return False

    def _apply_via_file(self, tool: str, args: dict) -> LiveResult:
        op = _OP_FOR_TOOL.get(tool, tool.replace("pyagent_", ""))
        code, resp = run_op(op, args, self.project_path, self._catalog)
        return LiveResult(ok=(code == 0), mode="file",
                          result=resp if isinstance(resp, dict) else {},
                          fatal=(code == 2))

    def _quit_kdenlive_if_running(self) -> None:
        """If Kdenlive is running, quit it via D-Bus so it can't overwrite
        the file we're about to write. Falls back to SIGTERM/SIGKILL."""
        if self._dbus is None or not self._dbus.available:
            return
        try:
            if self._dbus.exit_app():
                for _ in range(50):
                    time.sleep(0.1)
                    if not self._dbus.available:
                        return
        except Exception:
            pass
        try:
            subprocess.run(["pkill", "-TERM", "-x", "kdenlive"],
                           timeout=5, check=False)
            for _ in range(30):
                time.sleep(0.1)
                r = subprocess.run(["pgrep", "-x", "kdenlive"],
                                   capture_output=True, check=False)
                if r.returncode != 0:
                    return
            subprocess.run(["pkill", "-KILL", "-x", "kdenlive"],
                           timeout=5, check=False)
        except Exception:
            pass

    def _notify_reload_needed(self) -> None:
        if self._dbus is not None and self._dbus.available:
            self._notifier(
                "PyAgent edit applied",
                "Timeline updated on disk. Reload (Ctrl+Shift+R) or reopen.",
            )
        else:
            self._notifier(
                "PyAgent edit applied",
                f"Edit written to {self.project_path}. Open in Kdenlive.",
            )

    def _source_id_to_url(self, source_id: str) -> str | None:
        try:
            from lxml import etree
            tree = etree.parse(self.project_path)
            for producer in tree.iter("producer"):
                if producer.get("id") == source_id:
                    for prop in producer.iter("property"):
                        if prop.get("name") == "resource":
                            return prop.text
        except Exception:
            return None
        return None
