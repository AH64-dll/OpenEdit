"""Style profile persistence (pinned overrides).

Per phase4-design-revised.md section 3.2 and spec section 8.6.
"""
from __future__ import annotations

import json
import os
import shutil
import sys

from open_edit.storage.config import get_config_dir, get_profile_path


def set_pinned(key: str, value) -> None:
    profile = json.loads(get_profile_path().read_text())
    profile.setdefault("pinned", {})[key] = value
    _write_profile_with_backup(profile)


def _write_profile_with_backup(profile: dict) -> None:
    profile_path = get_profile_path()
    config_dir = get_config_dir()
    # Rotate last 3 versions
    for i in range(2, 0, -1):
        src = config_dir / f"style_profile_v{i}.json.bak"
        dst = config_dir / f"style_profile_v{i+1}.json.bak"
        if src.exists():
            shutil.copy2(src, dst)
    if profile_path.exists():
        shutil.copy2(profile_path, config_dir / "style_profile_v1.json.bak")
    # Clean up old backups beyond 3
    for f in config_dir.glob("style_profile_v[4-9]*.json.bak"):
        f.unlink()
    profile_path.write_text(json.dumps(profile, indent=2))
    if sys.platform != "win32":
        os.chmod(profile_path, 0o600)
