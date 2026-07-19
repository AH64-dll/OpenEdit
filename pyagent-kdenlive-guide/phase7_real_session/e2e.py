"""phase7_real_session.e2e — the ONE entry point for the real-session e2e.

Owns the skipif helpers, XvfbContext, KdenliveLaunch, ChatUIServer,
read_timeline_state, and re-exports WSClient. ``tests/test_e2e.py`` is
the single test that drives a real pi against a real kdenlive in xvfb.
The deleted modules (chat_ui, dbus_probe, kdenlive, skipif_helpers) are
absorbed into this file.
"""
from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from lxml import etree

from phase7_real_session.ws_client import WSClient


# skipif helpers (bodies of @skipUnless / @skipIf)

def _has(name: str) -> bool:
    return shutil.which(name) is not None


def _has_opencode_auth() -> bool:
    return bool(os.environ.get("OPENCODE_API_KEY")) or (
        Path.home() / ".pi" / "agent" / "auth.json"
    ).is_file()


_DBUS_LIST_NAMES = [
    "dbus-send", "--session", "--print-reply",
    "--dest=org.freedesktop.DBus", "/org/freedesktop/DBus",
    "org.freedesktop.DBus.ListNames",
]


def _kdenlive_already_on_bus() -> bool:
    try:
        out = subprocess.run(_DBUS_LIST_NAMES, capture_output=True,
                             text=True, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return "kdenlive" in (out.stdout or "").lower()


def _terminate_proc(proc: Optional[subprocess.Popen]) -> None:
    """SIGTERM the process group; SIGKILL after 5s. Safe on dead procs."""
    if proc is None:
        return
    try:
        pgid = os.getpgid(proc.pid)
    except ProcessLookupError:
        return
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=5.0)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        proc.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        pass


def _pick_free_port() -> int:
    s = socket.socket()
    s.bind(("", 0))
    p = s.getsockname()[1]
    s.close()
    return p


# XvfbContext

class XvfbContext:
    """Start Xvfb on the first free display in [min, max]; SIGTERM on exit."""

    def __init__(self, min_display: int = 99, max_display: int = 199,
                 binary: str = "Xvfb") -> None:
        self._min, self._max, self._binary = min_display, max_display, binary
        self._proc: Optional[subprocess.Popen] = None
        self._display = ""

    @property
    def display(self) -> str:
        return self._display

    def __enter__(self) -> str:
        if shutil.which(self._binary) is None and not os.path.isfile(self._binary):
            raise RuntimeError(
                f"Xvfb binary not found: {self._binary!r} (install xorg-server-xvfb)"
            )
        for n in range(self._min, self._max + 1):
            try:
                self._proc = subprocess.Popen(
                    [self._binary, f":{n}", "-ac", "-screen", "0", "1024x768x24"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    preexec_fn=os.setsid,
                )
            except OSError:
                continue
            time.sleep(0.2)
            if self._proc.poll() is None:
                self._display = f":{n}"
                return self._display
        raise RuntimeError(f"No free display in [{self._min}, {self._max}]")

    def __exit__(self, *exc) -> None:
        _terminate_proc(self._proc)
        self._proc = None
        self._display = ""


# KdenliveLaunch

class KdenliveLaunch:
    """Launch kdenlive; wait for org.kde.kdenlive on the session D-Bus."""

    def __init__(self, project_path: str, display: str,
                 xdg_config_home: str, xdg_cache_home: str,
                 timeout: float = 30.0, binary: str = "kdenlive") -> None:
        if shutil.which(binary) is None and not os.path.isfile(binary):
            raise RuntimeError(f"kdenlive binary not found: {binary!r}")
        os.makedirs(xdg_config_home, exist_ok=True)
        os.makedirs(xdg_cache_home, exist_ok=True)
        self._p, self._d, self._t, self._bin = project_path, display, timeout, binary
        self._xc, self._xk = xdg_config_home, xdg_cache_home
        self._proc: Optional[subprocess.Popen] = None
        self._err: Optional[str] = None

    def _spawn(self) -> None:
        env = {**os.environ, "DISPLAY": self._d,
               "XDG_CONFIG_HOME": self._xc, "XDG_CACHE_HOME": self._xk}
        self._err = os.path.join(self._xk, "kdenlive.stderr")
        fp = open(self._err, "w")
        self._proc = subprocess.Popen(
            [self._bin, "--no-welcome", self._p],
            env=env, stdout=subprocess.DEVNULL, stderr=fp, preexec_fn=os.setsid,
        )
        fp.close()

    def wait_ready(self) -> None:
        if self._proc is None:
            self._spawn()
        deadline = time.time() + self._t
        while time.time() < deadline:
            if self._proc is not None and self._proc.poll() is not None:
                raise RuntimeError(
                    f"kdenlive exited with code {self._proc.returncode}; see {self._err}"
                )
            if _kdenlive_already_on_bus():
                return
            time.sleep(0.2)
        raise RuntimeError(
            f"kdenlive did not register on D-Bus within {self._t}s; see {self._err}"
        )

    def terminate(self) -> None:
        proc, self._proc = self._proc, None
        _terminate_proc(proc)


# ChatUIServer

class ChatUIServer:
    """Launch ``python3 -m phase4_chat_ui``; wait for /api/project=200."""

    def __init__(self, project_path: str, display: str,
                 provider: str = "opencode-go", model: str = "minimax-m3",
                 timeout: float = 15.0, port: int = 0,
                 command: Optional[list] = None) -> None:
        self._p, self._d, self._t = project_path, display, timeout
        self._port = port if port != 0 else _pick_free_port()
        self._cmd = command if command is not None else [
            "python3", "-m", "phase4_chat_ui",
            "--project", project_path, "--port", str(self._port),
            "--provider", provider, "--model", model,
        ]
        self._proc: Optional[subprocess.Popen] = None
        self._err: Optional[str] = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._port}"

    def _spawn(self) -> None:
        self._err = os.path.join(
            os.path.dirname(self._p) or ".", "chat_ui.stderr",
        )
        fp = open(self._err, "w")
        self._proc = subprocess.Popen(
            self._cmd, env={**os.environ, "DISPLAY": self._d},
            stdout=subprocess.DEVNULL, stderr=fp, preexec_fn=os.setsid,
        )
        fp.close()

    def wait_ready(self) -> None:
        if self._proc is None:
            self._spawn()
        deadline = time.time() + self._t
        last_err: Optional[Exception] = None
        while time.time() < deadline:
            if self._proc is not None and self._proc.poll() is not None:
                raise RuntimeError(
                    f"chat UI exited with code {self._proc.returncode}; see {self._err}"
                )
            try:
                with urllib.request.urlopen(f"{self.url}/api/project", timeout=1.0) as r:
                    if r.status == 200:
                        return
            except (urllib.error.URLError, ConnectionError, OSError) as e:
                last_err = e
            time.sleep(0.2)
        raise RuntimeError(f"chat UI did not become ready within {self._t}s: {last_err}")

    def terminate(self) -> None:
        proc, self._proc = self._proc, None
        _terminate_proc(proc)


# read_timeline_state

def _property_value(transition: etree._Element, name: str) -> str:
    for prop in transition.findall("property"):
        if prop.get("name") == name:
            return (prop.text or "").strip()
    return ""


def _track_producer_id(mt: Optional[etree._Element], index: int) -> str:
    if mt is None:
        return ""
    tracks = mt.findall("track")
    if 0 <= index < len(tracks):
        return tracks[index].get("producer", "") or ""
    return ""


def _transitions_in_tractor(root: etree._Element) -> list[dict[str, str]]:
    """Return every <transition> across all <tractor> elements."""
    out: list[dict[str, str]] = []
    for tractor in root.findall("tractor"):
        mt = tractor.find("multitrack")
        for tr in tractor.findall("transition"):
            try:
                a = int(_property_value(tr, "a_track"))
            except ValueError:
                a = 0
            try:
                b = int(_property_value(tr, "b_track"))
            except ValueError:
                b = 0
            kind = (_property_value(tr, "kdenlive_id")
                    or _property_value(tr, "mlt_service"))
            out.append({
                "from_clip": _track_producer_id(mt, a),
                "to_clip": _track_producer_id(mt, b),
                "kind": kind,
            })
    return out


def read_timeline_state(project_path: Optional[str] = None) -> dict:
    """Read transitions from the .kdenlive XML. ``{"transitions": [...]}``.

    KdenliveDBus (phase5) is write-only — no ``get_transition_list()`` —
    so the project file is the source of truth.
    """
    if project_path is None:
        project_path = os.environ.get("PYAGENT_PROJECT")
    if not project_path:
        raise RuntimeError("read_timeline_state requires project_path= or PYAGENT_PROJECT env")
    if not os.path.isfile(project_path):
        raise FileNotFoundError(project_path)
    return {"transitions": _transitions_in_tractor(etree.parse(project_path).getroot())}


__all__ = [
    "_has", "_has_opencode_auth", "_kdenlive_already_on_bus",
    "XvfbContext", "KdenliveLaunch", "ChatUIServer", "WSClient",
    "read_timeline_state",
]
