"""Unit tests for dbus_probe.

The brief's original spec called for reading the live Kdenlive
timeline via D-Bus, but KdenliveDBus (phase5) is write-only:
no get_transition_list() method exists. So read_timeline_state
parses the project file (the .kdenlive XML), which is the
source of truth. These tests run against real project files,
not a mock client.
"""
from __future__ import annotations

import shutil
import tempfile
import textwrap
import unittest
from pathlib import Path

from phase7_real_session.dbus_probe import read_timeline_state


_FIXTURE_DEMO = (
    Path(__file__).resolve().parents[2]
    / "phase3_pyagent_core"
    / "tests"
    / "fixtures"
    / "demo.kdenlive"
)


def _write_kdenlike(tmp: Path, body: str) -> Path:
    """Write a minimal .kdenlive-shaped XML file to tmp/<name>."""
    p = tmp / "demo.kdenlive"
    p.write_text(textwrap.dedent(body))
    return p


class TestReadTimelineStateEmpty(unittest.TestCase):
    def setUp(self) -> None:
        if not _FIXTURE_DEMO.exists():
            self.skipTest(f"fixture not found: {_FIXTURE_DEMO}")
        self.tmp = Path(tempfile.mkdtemp(prefix="phase7_dbprobe_"))
        self.project = self.tmp / "demo.kdenlive"
        shutil.copy2(_FIXTURE_DEMO, self.project)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_returns_empty_when_no_transitions(self) -> None:
        # The real demo.kdenlive fixture has no <transition> elements.
        state = read_timeline_state(project_path=str(self.project))
        self.assertEqual(state, {"transitions": []})


class TestReadTimelineStateWithTransitions(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="phase7_dbprobe_"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_returns_single_dissolve_transition(self) -> None:
        # Minimal valid .kdenlive: one multitrack with two tracks,
        # one <transition> between them (a_track=0, b_track=1,
        # kdenlive_id="luma" which is the standard "dissolve").
        self._write_two_tracks_one_transition()
        state = read_timeline_state(project_path=str(self.tmp / "demo.kdenlive"))
        self.assertEqual(len(state["transitions"]), 1)
        t = state["transitions"][0]
        self.assertEqual(t["from_clip"], "playlist0")
        self.assertEqual(t["to_clip"], "playlist1")
        self.assertEqual(t["kind"], "luma")

    def test_returns_multiple_transitions_in_document_order(self) -> None:
        self._write_two_tracks_two_transitions()
        state = read_timeline_state(project_path=str(self.tmp / "demo.kdenlive"))
        self.assertEqual(len(state["transitions"]), 2)
        self.assertEqual(state["transitions"][0]["kind"], "luma")
        self.assertEqual(state["transitions"][1]["kind"], "mix")

    def test_raises_without_project_path(self) -> None:
        with self.assertRaises(RuntimeError):
            read_timeline_state(project_path=None)

    def test_raises_on_missing_file(self) -> None:
        with self.assertRaises(FileNotFoundError):
            read_timeline_state(project_path=str(self.tmp / "does_not_exist.kdenlive"))

    def _write_two_tracks_one_transition(self) -> None:
        _write_kdenlike(self.tmp, """\
            <?xml version='1.0' encoding='utf-8'?>
            <mlt version="7.40.0" producer="main_bin" LC_NUMERIC="C" root="/tmp">
              <playlist id="main_bin"/>
              <playlist id="playlist0">
                <entry producer="producer_4" in="00:00:00.000" out="00:00:04.000"/>
              </playlist>
              <playlist id="playlist1">
                <entry producer="producer_4" in="00:00:00.000" out="00:00:04.000"/>
              </playlist>
              <tractor id="main_tractor" in="00:00:00.000" out="00:00:04.000">
                <multitrack>
                  <track producer="playlist0"/>
                  <track producer="playlist1"/>
                </multitrack>
                <transition id="transition0" in="00:00:01.000" out="00:00:02.000">
                  <property name="a_track">0</property>
                  <property name="b_track">1</property>
                  <property name="mlt_service">luma</property>
                  <property name="kdenlive_id">luma</property>
                </transition>
              </tractor>
            </mlt>
            """)

    def _write_two_tracks_two_transitions(self) -> None:
        _write_kdenlike(self.tmp, """\
            <?xml version='1.0' encoding='utf-8'?>
            <mlt version="7.40.0" producer="main_bin" LC_NUMERIC="C" root="/tmp">
              <playlist id="main_bin"/>
              <playlist id="playlist0">
                <entry producer="producer_4" in="00:00:00.000" out="00:00:10.000"/>
              </playlist>
              <playlist id="playlist1">
                <entry producer="producer_4" in="00:00:00.000" out="00:00:10.000"/>
              </playlist>
              <tractor id="main_tractor" in="00:00:00.000" out="00:00:10.000">
                <multitrack>
                  <track producer="playlist0"/>
                  <track producer="playlist1"/>
                </multitrack>
                <transition id="transition0" in="00:00:02.000" out="00:00:03.000">
                  <property name="a_track">0</property>
                  <property name="b_track">1</property>
                  <property name="kdenlive_id">luma</property>
                </transition>
                <transition id="transition1" in="00:00:05.000" out="00:00:06.000">
                  <property name="a_track">0</property>
                  <property name="b_track">1</property>
                  <property name="kdenlive_id">mix</property>
                </transition>
              </tractor>
            </mlt>
            """)


if __name__ == "__main__":
    unittest.main()
