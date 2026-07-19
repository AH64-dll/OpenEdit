"""CLI: notify the user that a project file changed, and trigger a reload
if Kdenlive is running."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from phase5_dbus_sync.dbus_client import KdenliveDBus, detect_service_name, is_running
from phase5_dbus_sync.live_sync import LiveSync, notify


def _cmd_apply(args: argparse.Namespace) -> int:
    payload = json.loads(sys.stdin.read() or "{}")
    project = payload.get("project")
    tool = payload.get("tool")
    tool_args = payload.get("args", {})
    if not project or not tool:
        print("error: project+tool required", file=sys.stderr)
        return 2
    if not Path(project).is_file():
        print(f"error: project file not found: {project}", file=sys.stderr)
        return 2
    result = LiveSync(project).apply(tool, tool_args).to_dict()
    if not result.get("ok", False) and result.get("error"):
        print(f"error: {result['error']}", file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


def _cmd_notify(args: argparse.Namespace) -> int:
    if not is_running():
        notify("PyAgent", f"Project {args.file} updated. Open it in Kdenlive to see changes.")
        return 0
    svc = detect_service_name()
    if svc is None:
        notify("PyAgent", f"Project {args.file} updated. Reopen in Kdenlive.")
        return 0
    dbus = KdenliveDBus(svc)
    if dbus.clean_restart(clean=False):
        notify("PyAgent", "Project reloaded in Kdenlive.")
        return 0
    notify("PyAgent", f"Project {args.file} updated. Reopen in Kdenlive.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Phase 5 D-Bus live sync")
    sub = p.add_subparsers(dest="cmd", required=True)
    p_apply = sub.add_parser("apply", help="apply a tool call via LiveSync (stdin JSON)")
    p_apply.set_defaults(func=_cmd_apply)
    p_notify = sub.add_parser("notify", help="notify user + reload if Kdenlive running")
    p_notify.add_argument("--file", required=True, help=".kdenlive file that changed")
    p_notify.set_defaults(func=_cmd_notify)
    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
