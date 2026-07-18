"""jeepney-based client for Kdenlive's org.kde.kdenlive.MainWindow D-Bus."""
from __future__ import annotations

from jeepney import new_method_call
from jeepney.io.blocking import open_dbus_connection


SERVICE = "org.kde.kdenlive"
PATH = "/kdenlive/MainWindow_1"
INTERFACE = "org.kde.kdenlive.MainWindow"


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
        if self._conn is None:
            return False
        try:
            msg = new_method_call(
                (self.service, self.path, self.interface),
                method, signature, args,
            )
            self._conn.send_and_get_reply(msg, timeout=2000)
            return True
        except Exception:
            return False

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
        # Single-bool overload: cleanRestart(false) reloads the *current*
        # open project from disk in place (window stays open). The (b,b)
        # overload with forceQuit=True instead quits Kdenlive, which is
        # why edits only appeared after a manual close/reopen.
        return self._call("cleanRestart", "b", clean)

    def exit_app(self) -> bool:
        return self._call("exitApp", "")
