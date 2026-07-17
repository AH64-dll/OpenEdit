"""Tests for the project file watcher."""
import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from phase4_chat_ui import watcher  # noqa: E402

FIXTURE = _REPO_ROOT / "phase4_chat_ui" / "tests" / "fixtures" / "demo.kdenlive"


class TestWatcher(unittest.TestCase):
    def test_watch_fires_on_modify(self):
        tmp = tempfile.mkdtemp()
        project = os.path.join(tmp, "work.kdenlive")
        with open(FIXTURE, "rb") as src, open(project, "wb") as dst:
            dst.write(src.read())

        fired = []

        async def handler(path: str) -> None:
            fired.append(path)

        async def run():
            task = asyncio.create_task(
                watcher.watch_project(project, handler, poll_delay_ms=50)
            )
            await asyncio.sleep(0.2)
            # Modify the file.
            with open(project, "ab") as f:
                f.write(b"<!-- touch -->")
            await asyncio.sleep(0.4)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        asyncio.run(asyncio.wait_for(run(), timeout=10))
        self.assertTrue(fired, "on_change should fire after file modification")


if __name__ == "__main__":
    unittest.main()
