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
LIVE_CAPABLE: frozenset[str] = frozenset({
    "pyagent_import_media",
    "pyagent_append_clip",
    "pyagent_apply_effect",
})

# Tools that change the timeline and should trigger a reload/notify when
# applied via the file backend (because Kdenlive won't see them otherwise).
RELOAD_AFTER: frozenset[str] = frozenset({
    "pyagent_insert_clip", "pyagent_move_clip", "pyagent_trim_clip",
    "pyagent_delete_clip", "pyagent_add_transition", "pyagent_add_marker",
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
        self._last_mode: str | None = None
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
                self._last_mode = "live"
                return {"ok": True, "result": {"mode": "live"}, "mode": "live"}
            # Fall through to file if D-Bus call failed.
        return self._apply_file(tool, args)

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
        self._last_mode = "file"
        mode = "fallback" if tool in LIVE_CAPABLE else "file"
        if tool in RELOAD_AFTER or tool in LIVE_CAPABLE:
            self._notifier(
                "PyAgent edit applied",
                f"{tool} written to {self.project_path}. Reopen in Kdenlive to see it."
                if mode == "file" else
                f"{tool} applied via file (D-Bus unavailable). Reopen to see it.",
            )
        return {"ok": code == 0, "result": resp, "mode": self._last_mode,
                "fatal": code == 2}

    def reload_if_needed(self) -> None:
        if self._last_mode == "file" and self._dbus is not None:
            self._dbus.clean_restart(clean=False, force_quit=True)
