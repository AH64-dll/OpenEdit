# MCP-Kdenlive & Kdenlive-API Integration Guide

This guide details how to leverage and adapt code patterns from the open-source projects [D-Ogi/mcp-kdenlive](https://github.com/D-Ogi/mcp-kdenlive) and [D-Ogi/kdenlive-api](https://github.com/D-Ogi/kdenlive-api) to extend PyAgent's live editing capabilities.

---

## 1. Overview of the Ecosystem

The `mcp-kdenlive` project enables LLM agents to interactively edit videos within Kdenlive using natural language. It divides responsibilities across three components:

1.  **AI Coding Assistant (Claude Code / Cursor)**: Communicates with an MCP client.
2.  **MCP Server (`mcp-kdenlive` + `kdenlive-api`)**: Translates high-level editing prompts (e.g., "Add transition between clip A and B") into Resolve-style API calls and sends them over D-Bus.
3.  **Patched Kdenlive Build (`D-Ogi/kdenlive`)**: A custom C++ fork of Kdenlive that exposes a scripting D-Bus interface (`org.kde.kdenlive.scripting`) using `Q_SCRIPTABLE` macros.

### Architecture Comparison

| Feature | Standard Kdenlive (Unmodified) | Patched Kdenlive (D-Ogi Fork) |
| :--- | :--- | :--- |
| **D-Bus Service** | `org.kde.kdenlive` | `org.kde.kdenlive` |
| **D-Bus Interface** | `org.kde.kdenlive.MainWindow` | `org.kde.kdenlive.scripting` |
| **Scripting Control** | High-level MainWindow triggers (no return values) | Low-level timeline query/manipulation (Resolve compatible) |
| **Portability** | **High** (runs out-of-the-box on any Linux install) | **Low** (requires compilation of custom C++ fork) |

---

## 2. Building the Patched Kdenlive

To unlock the full scripting interface, you must compile the custom Kdenlive fork from source.

### Setup Prerequisites (Ubuntu/Debian)
```bash
sudo apt update
sudo apt install -y build-essential cmake git extra-cmake-modules \
    libkf5archive-dev libkf5config-dev libkf5configwidgets-dev \
    libkf5coreaddons-dev libkf5dbusaddons-dev libkf5filemetadata-dev \
    libkf5i18n-dev libkf5kio-dev libkf5newstuff-dev libkf5notifications-dev \
    libkf5notifyconfig-dev libkf5solid-dev libkf5widgetsaddons-dev \
    libkf5xmlgui-dev libmlt-dev libmlt++-dev qtdeclarative5-dev \
    qtmultimedia5-dev qml-module-qtquick-controls2 qml-module-qtquick-layouts
```

### Cloning and Building the Fork
```bash
git clone --recursive https://github.com/D-Ogi/kdenlive.git
cd kdenlive
mkdir build && cd build
cmake .. -DCMAKE_INSTALL_PREFIX=/usr/local -DKDE_INSTALL_USE_QT_SYS_PATHS=ON
make -j$(nproc)
sudo make install
```
Verify the installation by listing session D-Bus interfaces while Kdenlive is open:
```bash
qdbus org.kde.kdenlive /kdenlive/MainWindow_1
```

---

## 3. Reference: Resolve-Style Scripting Commands

The table below lists key scripting methods introduced in `kdenlive-api`. You can use these names as reference designs for custom script generation in PyAgent:

| DaVinci Resolve Style Method | Purpose / Kdenlive Translation | D-Bus Endpoint Signature |
| :--- | :--- | :--- |
| `ImportMedia(paths)` | Adds files to the Project Bin | `addProjectClip(url, folder)` |
| `InsertClipToTimeline(clip, track)` | Appends or inserts a clip to a specific timeline track | `insertTimelineClip(track_idx, clip_id, start_frame)` |
| `AddTransition(clipA, clipB, type)` | Inserts a transition between two adjacent clips | `addTimelineTransition(track_idx, clipA_id, clipB_id, type)` |
| `GetProjectName()` | Returns the name of the active project file | `getProjectName() -> s` |
| `GetTimelineDuration()` | Retrieves length of the sequence | `getTimelineDuration() -> x` |
| `AddEffect(clip, effect_id)` | Appends video/audio effect to clip | `addEffectToClip(clip_id, effect_id)` |

---

## 4. Extending `dbus_client.py` for PyAgent

We can extend PyAgent's `KdenliveDBus` to natively handle both **Standard** methods (MainWindow interface) and **Scripting** methods (Scripting interface). This allows PyAgent to gracefully fall back on unmodified builds while enabling rich features when a patched build is detected.

### Code Pattern Example for `dbus_client.py`

```python
"""Extended client supporting both Standard and Patched Kdenlive D-Bus interfaces."""
from __future__ import annotations

import logging
from jeepney import new_method_call
from jeepney.io.blocking import open_dbus_connection

logger = logging.getLogger(__name__)

SERVICE = "org.kde.kdenlive"
PATH_MAIN = "/kdenlive/MainWindow_1"
INTERFACE_MAIN = "org.kde.kdenlive.MainWindow"
INTERFACE_SCRIPT = "org.kde.kdenlive.scripting"


class KdenliveDBus:
    def __init__(self, service: str = SERVICE) -> None:
        self.service = service
        self._conn = None
        self._has_scripting = None

    def _ensure_conn(self) -> None:
        if self._conn is None:
            self._conn = open_dbus_connection(bus="SESSION")

    def _call(self, path: str, interface: str, method: str, signature: str, *args) -> bool:
        try:
            self._ensure_conn()
            msg = new_method_call(
                (self.service, path, interface),
                method, signature, args,
            )
            self._conn.send_and_get_reply(msg, timeout=2000)
            return True
        except Exception as e:
            logger.debug(f"D-Bus call {method} failed: {e}")
            return False

    @property
    def has_scripting_api(self) -> bool:
        """Probe if Kdenlive supports org.kde.kdenlive.scripting interface."""
        if self._has_scripting is not None:
            return self._has_scripting
        # Test call to getProjectName on scripting interface
        success = self._call(PATH_MAIN, INTERFACE_SCRIPT, "getProjectName", "")
        self._has_scripting = success
        return success

    # --- Standard Methods (Exposed in all builds) ---

    def add_project_clip(self, url: str, folder: str = "") -> bool:
        """Add media asset to the bin."""
        return self._call(PATH_MAIN, INTERFACE_MAIN, "addProjectClip", "ss", url, folder)

    def add_timeline_clip(self, url: str) -> bool:
        """Append media directly to the first active track."""
        return self._call(PATH_MAIN, INTERFACE_MAIN, "addTimelineClip", "s", url)

    def clean_restart(self, clean: bool = False) -> bool:
        """Reload project XML from disk in place."""
        return self._call(PATH_MAIN, INTERFACE_MAIN, "cleanRestart", "b", clean)

    # --- Scripting Methods (Requires D-Ogi fork / mcp-kdenlive) ---

    def insert_clip_to_track(self, track_index: int, clip_id: str, start_frame: int) -> bool:
        """Insert clip at specific track index and frame."""
        if not self.has_scripting_api:
            logger.warning("Advanced scripting requires Kdenlive scripting build.")
            return False
        return self._call(PATH_MAIN, INTERFACE_SCRIPT, "insertTimelineClip", "isi", track_index, clip_id, start_frame)

    def get_timeline_duration(self) -> int | None:
        """Get timeline duration in frames."""
        if not self.has_scripting_api:
            return None
        # Custom call returning int/long
        try:
            self._ensure_conn()
            msg = new_method_call(
                (self.service, PATH_MAIN, INTERFACE_SCRIPT),
                "getTimelineDuration", "", ()
            )
            reply = self._conn.send_and_get_reply(msg, timeout=2000)
            return reply[0]
        except Exception:
            return None
```
