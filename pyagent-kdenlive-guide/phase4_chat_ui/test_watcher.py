"""Tests for the project file watcher."""
import asyncio
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from phase4_chat_ui import watcher  # noqa: E402

FIXTURE = _REPO_ROOT / "phase4_chat_ui" / "tests" / "fixtures" / "demo.kdenlive"


def _copy_fixture_to(path: str) -> None:
    with open(FIXTURE, "rb") as src, open(path, "wb") as dst:
        dst.write(src.read())


class TestWatcher(unittest.TestCase):
    def test_watch_fires_on_modify(self):
        tmp = tempfile.mkdtemp()
        project = os.path.join(tmp, "work.kdenlive")
        _copy_fixture_to(project)

        fired = []

        async def handler(path: str) -> None:
            fired.append(path)

        async def run():
            task = asyncio.create_task(
                watcher.watch_project(project, handler, poll_delay_ms=50)
            )
            await asyncio.sleep(0.2)
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

    def test_unrelated_sibling_change_does_not_fire(self):
        """Regression: writes to a sibling file in the same directory must
        not be reported as a project change. Only changes whose file mtime
        is within the watcher's mtime window of the project file are kept.
        """
        tmp = tempfile.mkdtemp()
        project = os.path.join(tmp, "work.kdenlive")
        sibling = os.path.join(tmp, "unrelated.txt")
        _copy_fixture_to(project)
        with open(sibling, "wb") as f:
            f.write(b"unrelated")

        # Push the project's mtime 60s into the past so the mtime-window
        # check is unambiguous: a write to the sibling bumps *its* mtime to
        # "now" while the project's stays at now-60s — a 60s gap, well
        # outside the 1.0s default window.
        old = time.time() - 60.0
        os.utime(project, (old, old))
        os.utime(sibling, (old, old))

        fired: list[str] = []

        async def handler(path: str) -> None:
            fired.append(path)

        async def run():
            task = asyncio.create_task(
                watcher.watch_project(project, handler, poll_delay_ms=50)
            )
            await asyncio.sleep(0.2)
            # Modify an unrelated file. Project mtime stays at `old`.
            with open(sibling, "ab") as f:
                f.write(b"unrelated touch")
            await asyncio.sleep(0.5)
            self.assertEqual(
                fired, [],
                "on_change should not fire for an unrelated sibling write",
            )
            # Now modify the project file. This must fire.
            with open(project, "ab") as f:
                f.write(b"<!-- project touch -->")
            await asyncio.sleep(0.5)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        asyncio.run(asyncio.wait_for(run(), timeout=10))
        self.assertEqual(
            len(fired), 1,
            "on_change should fire exactly once (only for the project edit)",
        )


if __name__ == "__main__":
    unittest.main()
