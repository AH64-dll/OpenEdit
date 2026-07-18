"""LiveSync: routes mutating ops to D-Bus (live) or file backend (reload)."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

# Make Phase 3 importable (it lives in a sibling package at repo root).
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from phase3_pyagent_core.__main__ import run_op  # noqa: E402

from phase5_dbus_sync.dbus_client import KdenliveDBus  # noqa: E402
from phase5_dbus_sync.kdenlive_state import detect_service_name  # noqa: E402
from phase5_dbus_sync.notifier import notify  # noqa: E402

# Tools where upstream Kdenlive's D-Bus can do the work live.
#
# NOTE: on the Kdenlive 26.04 build we target, the live D-Bus methods
# (addTimelineClip / addProjectClip / cleanRestart) are UNSTABLE and crash
# the running Kdenlive instance ("Remote peer disconnected"). Routing edits
# through them destroys the user's open window. So we intentionally do
# ALL mutating ops via the file backend (which we verified writes a valid
# file that Kdenlive reloads cleanly on reopen) and simply notify the
# user to reload. This is the reliable path.
LIVE_CAPABLE: frozenset[str] = frozenset()

# Tools that change the timeline and should trigger a reload/notify when
# applied via the file backend (because Kdenlive won't see them otherwise).
RELOAD_AFTER: frozenset[str] = frozenset({
    "pyagent_import_media", "pyagent_insert_clip", "pyagent_append_clip",
    "pyagent_move_clip", "pyagent_trim_clip", "pyagent_delete_clip",
    "pyagent_add_transition", "pyagent_apply_effect", "pyagent_add_marker",
    "pyagent_save_project",
})

# Map the pi tool name to the Phase 3 backend op name used by run_op.
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


def _default_catalog() -> str:
    p = _REPO_ROOT / "phase1_knowledge_base" / "catalog.json"
    return str(p)


class LiveSync:
    def __init__(self, project_path: str,
                 dbus: KdenliveDBus | None = None,
                 notifier: Callable[[str, str], None] = notify) -> None:
        self.project_path = project_path
        self._notifier = notifier
        # Lazily resolve the running instance.
        service = detect_service_name()
        self._dbus = dbus or (KdenliveDBus(service) if service else None)
        self._catalog = _default_catalog()

    def is_live(self, tool: str) -> bool:
        return tool in LIVE_CAPABLE and self._dbus is not None and self._dbus.available

    def apply(self, tool: str, args: dict) -> dict:
        if self.is_live(tool):
            ok = self._apply_live(tool, args)
            if ok:
                return {"ok": True, "result": {"mode": "live"}, "mode": "live"}
            # Fall through to file if D-Bus call failed.
        result = self._apply_file(tool, args)
        # Make every file-mode edit show up in the already-open Kdenlive
        # window. Kdenlive's D-Bus only exposes add-clip/effect live methods,
        # so for the remaining mutating ops we reload the current project
        # in place (cleanRestart with clean=False) — the open window
        # refreshes from disk and shows the edit with a brief flicker.
        if result.get("ok") and tool in RELOAD_AFTER:
            self._auto_reload()
        return result

    def _auto_reload(self) -> None:
        """After a file-mode edit, let the user see it in their open Kdenlive.

        On the Kdenlive 26.04 build we target, `cleanRestart` is UNSTABLE
        and frequently crashes the running instance. So we do NOT call it blindly.
        Instead we attempt a guarded reload: try cleanRestart once; if Kdenlive
        is dead afterward, relaunch it on the (now-updated) project file. Either
        way the edit is on disk and will be visible after a reload/reopen.
        """
        kdenlive_was_up = self._dbus is not None and self._dbus.available
        if kdenlive_was_up:
            # Best-effort in-place reload. If it crashes Kdenlive, we
            # detect that below and relaunch.
            try:
                self._dbus.clean_restart(clean=False)
            except Exception:
                pass
            # Give Kdenlive a moment, then check it survived.
            import time
            time.sleep(2)
            if not (self._dbus.available):
                self._relaunch_kdenlive()
                self._notifier(
                    "PyAgent edit applied",
                    "Timeline reloaded in a fresh Kdenlive window.",
                )
                return
            self._notifier(
                "PyAgent edit applied",
                "Timeline updated. If the window didn't refresh, reload the "
                "project (Ctrl+Shift+R) or reopen it.",
            )
            return
        # No live instance — notify so the user knows to reopen.
        self._notifier(
            "PyAgent edit applied",
            f"Edit written to {self.project_path}. Open it in Kdenlive to see it.",
        )

    def _relaunch_kdenlive(self) -> None:
        """Relaunch Kdenlive on the project after a crash during reload."""
        import subprocess
        try:
            subprocess.Popen(
                ["kdenlive", self.project_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception:
            pass

    def _apply_live(self, tool: str, args: dict) -> bool:
        assert self._dbus is not None
        if tool == "pyagent_import_media":
            # import_media takes `paths`; use the first one as the URL.
            paths = args.get("paths") or []
            url = paths[0] if paths else args.get("path", "")
            return bool(url) and self._dbus.add_project_clip(str(url))
        if tool == "pyagent_append_clip":
            # addTimelineClip adds the given URL to the end of the active
            # track. We map source_id -> url via the project file.
            url = self._source_id_to_url(args.get("source_id", ""))
            return self._dbus.add_timeline_clip(url) if url else False
        if tool == "pyagent_apply_effect":
            return self._dbus.add_effect(str(args.get("effect_id", "")))
        return False

    def _source_id_to_url(self, source_id: str) -> str | None:
        """Look up the bin clip's resource URL for a source_id in the project file."""
        try:
            from lxml import etree
            tree = etree.parse(self.project_path)
            root = tree.getroot()
            for producer in root.iter("producer"):
                if producer.get("id") == source_id:
                    for prop in producer.iter("property"):
                        if prop.get("name") == "resource":
                            return prop.text
        except Exception:
            return None
        return None

    def _apply_file(self, tool: str, args: dict) -> dict:
        op = _OP_FOR_TOOL.get(tool, tool.replace("pyagent_", ""))
        code, resp = run_op(op, args, self.project_path, self._catalog)
        return {"ok": code == 0, "result": resp, "mode": "file",
                "fatal": code == 2}
