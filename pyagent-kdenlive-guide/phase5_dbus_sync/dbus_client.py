"""jeepney-based client for Kdenlive's org.kde.kdenlive D-Bus interfaces.

Also exposes two small process-discovery helpers (`is_running`,
`detect_service_name`) that used to live in a separate
`kdenlive_state.py` module; they were inlined here because every caller
already imported `KdenliveDBus` from this file, and the split module
added no value.
"""
from __future__ import annotations

import shutil
import subprocess
from typing import Any

from jeepney import new_method_call
from jeepney.io.blocking import open_dbus_connection


SERVICE = "org.kde.kdenlive"
PATH = "/kdenlive/MainWindow_1"
INTERFACE = "org.kde.kdenlive.MainWindow"


def is_running() -> bool:
    """True if `pgrep` finds a kdenlive process."""
    if shutil.which("pgrep") is None:
        return False
    r = subprocess.run(
        ["pgrep", "-x", "kdenlive"],
        capture_output=True, text=True,
    )
    return r.returncode == 0 and bool(r.stdout.strip())


def detect_service_name() -> str | None:
    """Return the actual D-Bus service name (e.g. `org.kde.kdenlive-2046260`)
    by listing bus names via `busctl`, or None if not found."""
    if shutil.which("busctl") is None:
        return SERVICE if is_running() else None
    r = subprocess.run(
        ["busctl", "--user", "list"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        return SERVICE if is_running() else None
    for line in r.stdout.splitlines():
        if "org.kde.kdenlive" in line:
            return line.split()[0]
    return None


class KdenliveDBus:
    """Thin wrapper. All methods are no-throw and return bool success."""

    def __init__(self, service: str = SERVICE, path: str = PATH,
                 interface: str = INTERFACE) -> None:
        self.service = service
        self.path = path
        self.interface = interface
        self._conn = None

    @property
    def available(self) -> bool:
        try:
            self._ensure_conn()
            return self._conn is not None
        except Exception:
            return False

    def _ensure_conn(self) -> None:
        if self._conn is not None:
            return
        self._conn = open_dbus_connection(bus="SESSION")

    def _call(self, method: str, signature: str, *args) -> bool:
        success, _ = self._call_with_reply(self.path, self.interface, method, signature, *args)
        return success

    def _call_with_reply(self, path: str, interface: str, method: str, signature: str, *args) -> tuple[bool, Any]:
        try:
            self._ensure_conn()
            if self._conn is None:
                return False, None
            msg = new_method_call(
                (self.service, path, interface),
                method, signature, args,
            )
            reply = self._conn.send_and_get_reply(msg, timeout=2000)
            return True, reply
        except Exception:
            return False, None

    def add_project_clip(self, url: str, folder: str = "") -> bool:
        return self._call("addProjectClip", "ss", url, folder)

    def add_timeline_clip(self, url: str) -> bool:
        return self._call("addTimelineClip", "s", url)

    def add_effect(self, effect_id: str) -> bool:
        return self._call("addEffect", "s", effect_id)

    def script_render(self, url: str) -> bool:
        return self._call("scriptRender", "s", url)

    def update_project_path(self, path: str) -> bool:
        return self._call("updateProjectPath", "s", path)

    def clean_restart(self, clean: bool = False) -> bool:
        return self._call("cleanRestart", "b", clean)

    def exit_app(self) -> bool:
        return self._call("exitApp", "")

    @property
    def has_scripting_api(self) -> bool:
        """Check if Kdenlive supports the advanced org.kde.kdenlive.scripting interface."""
        success, _ = self._call_with_reply(
            self.path,
            "org.kde.kdenlive.scripting",
            "getProjectName",
            ""
        )
        return success

    def insert_clip_to_track(self, track_index: int, clip_id: str, start_frame: int) -> bool:
        """Insert clip at specific track index and frame (requires scripting build)."""
        success, _ = self._call_with_reply(
            self.path,
            "org.kde.kdenlive.scripting",
            "insertTimelineClip",
            "isi",
            track_index,
            clip_id,
            start_frame
        )
        return success

    def get_timeline_duration(self) -> int | None:
        """Get timeline duration in frames (requires scripting build)."""
        success, reply = self._call_with_reply(
            self.path,
            "org.kde.kdenlive.scripting",
            "getTimelineDuration",
            ""
        )
        if success and reply and len(reply) > 0:
            return reply[0]
        return None
