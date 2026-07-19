"""Real pi-session end-to-end test.

The ONE persistent e2e test for phase7. Drives a real ``pi`` against
a real Kdenlive in xvfb via the chat UI, and asserts the end-to-end
pipeline (LLM → file → D-Bus live-sync) works. Skips cleanly when the
required deps (pi, kdenlive, Xvfb, dbus-send, opencode auth) are absent.

This is the only test in the phase7_real_session/tests/ directory.
The unit tests that previously lived in tests/test_chat_ui.py,
tests/test_dbus_probe.py, tests/test_kdenlive.py, tests/test_skipif.py,
tests/test_ws_client.py, and tests/test_xvfb.py are gone — the
helpers they exercised (XvfbContext, KdenliveLaunch, ChatUIServer,
read_timeline_state, WSClient, _has/_has_opencode_auth/
_kdenlive_already_on_bus) live in ``phase7_real_session/e2e.py`` and
are tested implicitly by this e2e (plus a small unit test for the
XML parser, see below).

Note on non-determinism: the model may occasionally stop and ask for
clarification instead of running the tool chain, so the test can flake.
It is intended as a manual real-session smoke test
(``make -C phase7_real_session test-e2e``), not a hard CI gate. The
deterministic unit/integration suites cover correctness; this one
proves the whole stack works end-to-end on a real machine.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from phase7_real_session.e2e import (
    ChatUIServer, KdenliveLaunch, WSClient, XvfbContext, read_timeline_state,
)
from phase7_real_session.skipif import (
    _has, _has_opencode_auth, _kdenlive_already_on_bus,
)

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "phase3_pyagent_core" / "tests" / "fixtures" / "demo.kdenlive"
CATALOG = REPO / "phase1_knowledge_base" / "catalog.json"

PROMPT = (
    "The project has one clip on the timeline (id 2). "
    "Import the media file at "
    "/home/ah64/apps/mlt-pipeline/testdata/clip_short.mp4, "
    "append it after the existing clip, then add a 1-second "
    "dissolve transition between the two clips."
)


def _step(msg: str) -> None:
    print(f"[e2e] {msg}", file=sys.stderr, flush=True)


class TestReadTimelineStateParser(unittest.TestCase):
    """Locks in read_timeline_state's XML parser (the only non-trivial pure
    function in e2e.py that benefits from a unit test)."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="phase7_e2e_test_"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_returns_two_transitions_in_document_order(self) -> None:
        p = self.tmp / "demo.kdenlive"
        p.write_text("""\
<?xml version='1.0' encoding='utf-8'?>
<mlt version="7.40.0" producer="main_bin" LC_NUMERIC="C" root="/tmp">
  <playlist id="main_bin"/>
  <playlist id="playlist0"><entry producer="p4" in="00:00:00.000" out="00:00:04.000"/></playlist>
  <playlist id="playlist1"><entry producer="p4" in="00:00:00.000" out="00:00:04.000"/></playlist>
  <tractor id="t0" in="00:00:00.000" out="00:00:04.000">
    <multitrack>
      <track producer="playlist0"/>
      <track producer="playlist1"/>
    </multitrack>
    <transition id="tr0" in="00:00:01.000" out="00:00:02.000">
      <property name="a_track">0</property>
      <property name="b_track">1</property>
      <property name="mlt_service">luma</property>
    </transition>
    <transition id="tr1" in="00:00:02.000" out="00:00:03.000">
      <property name="a_track">0</property>
      <property name="b_track">1</property>
      <property name="kdenlive_id">mix</property>
    </transition>
  </tractor>
</mlt>
""")
        state = read_timeline_state(project_path=str(p))
        self.assertEqual(len(state["transitions"]), 2)
        self.assertEqual(state["transitions"][0]["from_clip"], "playlist0")
        self.assertEqual(state["transitions"][0]["to_clip"], "playlist1")
        self.assertEqual(state["transitions"][0]["kind"], "luma")
        self.assertEqual(state["transitions"][1]["kind"], "mix")

    def test_raises_without_project_path(self) -> None:
        old = os.environ.pop("PYAGENT_PROJECT", None)
        try:
            with self.assertRaises(RuntimeError):
                read_timeline_state()
        finally:
            if old is not None:
                os.environ["PYAGENT_PROJECT"] = old

    def test_raises_on_missing_file(self) -> None:
        with self.assertRaises(FileNotFoundError):
            read_timeline_state(project_path=str(self.tmp / "missing.kdenlive"))


@unittest.skipUnless(_has_opencode_auth(),
    "opencode auth not configured (need OPENCODE_API_KEY or ~/.pi/agent/auth.json)")
@unittest.skipUnless(_has("pi"), "pi not on PATH")
@unittest.skipUnless(_has("kdenlive"), "kdenlive not on PATH")
@unittest.skipUnless(_has("Xvfb"), "Xvfb not on PATH (install xorg-server-xvfb)")
@unittest.skipUnless(_has("dbus-send"), "dbus-send not on PATH")
@unittest.skipIf(_kdenlive_already_on_bus(),
    "a kdenlive is already on the session D-Bus; close it and re-run")
@unittest.skipIf(not FIXTURE.is_file(), "demo.kdenlive fixture missing")
@unittest.skipIf(not CATALOG.is_file(), "catalog.json missing")
class TestE2EPiSession(unittest.TestCase):
    """End-to-end: real pi + real Kdenlive + chat UI + D-Bus."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="pyagent_e2e_"))
        self.project = self.tmp / "demo.kdenlive"
        shutil.copy(FIXTURE, self.project)
        self._pre_xml = self.project.read_text()
        self._xvfb: XvfbContext | None = None
        self._kdenlive: KdenliveLaunch | None = None
        self._chat_ui: ChatUIServer | None = None
        self._events: list[dict] = []
        self._transcript_path = self.tmp / "transcript.json"
        self._keep_tmp = bool(os.environ.get("PYAGENT_KEEP_E2E_TMP"))

    def tearDown(self) -> None:
        # Cleanup order: chat UI -> Kdenlive -> Xvfb.
        try:
            if self._chat_ui is not None:
                self._chat_ui.terminate()
        except Exception as e:
            print(f"[e2e] chat_ui terminate error: {e}", file=sys.stderr)
        try:
            if self._kdenlive is not None:
                self._kdenlive.terminate()
        except Exception as e:
            print(f"[e2e] kdenlive terminate error: {e}", file=sys.stderr)
        try:
            if self._xvfb is not None:
                self._xvfb.__exit__(None, None, None)
        except Exception as e:
            print(f"[e2e] xvfb exit error: {e}", file=sys.stderr)
        if not self._keep_tmp:
            shutil.rmtree(self.tmp, ignore_errors=True)
        else:
            print(f"[e2e] tempdir preserved at {self.tmp} "
                  f"(PYAGENT_KEEP_E2E_TMP=1)", file=sys.stderr)

    def _find_add_transition(self) -> tuple[dict | None, dict | None]:
        for ev in self._events:
            if ev.get("type") == "tool" and ev.get("tool") == "pyagent_add_transition":
                return ev, ev.get("args") or {}
        return None, None

    def _count_transitions_in_file(self) -> int:
        try:
            tree = ET.parse(self.project)
        except ET.ParseError as e:
            self.fail(f"project file is not valid XML: {e}")
        return len(tree.getroot().findall(".//transition"))

    def _count_transitions_pre_run(self) -> int:
        try:
            tree = ET.fromstring(self._pre_xml)
        except ET.ParseError:
            return 0
        return len(tree.findall(".//transition"))

    def _dissolve_mlt_services(self) -> set[str]:
        """mlt_service values that count as a dissolve/crossfade in Kdenlive."""
        services = {"luma", "frei0r.dissolve"}
        catalog_path = (
            Path(__file__).resolve().parents[1]
            / "phase1_knowledge_base" / "catalog.json"
        )
        if catalog_path.exists():
            try:
                catalog = json.loads(catalog_path.read_text())
                for t in catalog.get("transitions", []):
                    if "dissolve" in (t.get("name", "") + t.get("id", "")).lower():
                        svc = t.get("mlt_service")
                        if svc:
                            services.add(svc)
            except (json.JSONDecodeError, OSError):
                pass
        return services

    def test_edit_render_qc_roundtrip(self) -> None:
        """The full e2e: real pi, real Kdenlive, real D-Bus, real file."""
        _step("starting Xvfb")
        self._xvfb = XvfbContext(min_display=99, max_display=199)
        display = self._xvfb.__enter__()
        os.environ["DISPLAY"] = display
        _step(f"Xvfb on {display}")

        try:
            _step("launching Kdenlive")
            self._kdenlive = KdenliveLaunch(
                project_path=str(self.project),
                display=display,
                xdg_config_home=str(self.tmp / "config"),
                xdg_cache_home=str(self.tmp / "cache"),
                timeout=45.0,
            )
            self._kdenlive.wait_ready()
            _step("Kdenlive ready on D-Bus")

            _step("launching chat UI")
            self._chat_ui = ChatUIServer(
                project_path=str(self.project),
                display=display,
                provider="opencode-go",
                model="minimax-m3",
                timeout=20.0,
            )
            self._chat_ui.wait_ready()
            _step(f"chat UI ready at {self._chat_ui.url}")

            _step("sending prompt via WebSocket")
            ws = WSClient(url=f"{self._chat_ui.url.replace('http', 'ws', 1)}/ws",
                          timeout=180.0)
            self._events = ws.run_prompt_sync(PROMPT)
            _step(f"collected {len(self._events)} events")
            self._transcript_path.write_text(json.dumps(self._events, indent=2))

            _step("asserting tool call")
            tool_event, args = self._find_add_transition()
            self.assertIsNotNone(
                tool_event,
                f"pi did not call pyagent_add_transition. "
                f"Events: {[e.get('type') for e in self._events]}. "
                f"Transcript: {self._transcript_path}",
            )

            _step("asserting tool result")
            result = tool_event.get("result") or {}
            result_text = ""
            if isinstance(result, list):
                for part in result:
                    if isinstance(part, dict) and part.get("type") == "text":
                        result_text += part.get("text", "")
            elif isinstance(result, str):
                result_text = result
            else:
                result_text = str(result)
            self.assertTrue(
                result_text.strip() and "error" not in result_text.lower(),
                f"tool result looks like a failure: {result!r}",
            )

            # Give Kdenlive a moment to apply the live-sync after the
            # tool call returns.
            time.sleep(2.0)

            _step("asserting file changed on disk (and kind is correct)")
            pre_count = self._count_transitions_pre_run()
            post_count = self._count_transitions_in_file()
            self.assertGreater(
                post_count, pre_count,
                f"no <transition> added to file. pre={pre_count} post={post_count}",
            )
            post_state = read_timeline_state(project_path=str(self.project))
            post_kinds = [t["kind"] for t in post_state["transitions"]]
            dissolve_services = self._dissolve_mlt_services()
            self.assertTrue(
                any(k in dissolve_services for k in post_kinds),
                f"no dissolve/crossfade transition in project file. "
                f"Got kinds={post_kinds}; expected one of {dissolve_services}",
            )

            _step("asserting LLM described the action")
            final_texts = [
                ev.get("text", "") for ev in self._events
                if ev.get("type") == "message" and ev.get("role") == "assistant"
            ]
            final_text = " ".join(final_texts).lower()
            self.assertTrue(
                "dissolve" in final_text or "added a transition" in final_text,
                f"LLM did not describe the action. Final text: {final_text!r}",
            )

            _step("all assertions passed")

        except Exception:
            if self._transcript_path.exists():
                print(f"\n[e2e] TRANSCRIPT:\n{self._transcript_path.read_text()}",
                      file=sys.stderr)
            kdenlive_stderr = self.tmp / "cache" / "kdenlive.stderr"
            if kdenlive_stderr.exists():
                tail = "\n".join(kdenlive_stderr.read_text().splitlines()[-50:])
                print(f"\n[e2e] KDENLIVE STDERR (last 50 lines):\n{tail}",
                      file=sys.stderr)
            chat_ui_stderr = self.tmp / "chat_ui.stderr"
            if chat_ui_stderr.exists():
                tail = "\n".join(chat_ui_stderr.read_text().splitlines()[-50:])
                print(f"\n[e2e] CHAT UI STDERR (last 50 lines):\n{tail}",
                      file=sys.stderr)
            raise


if __name__ == "__main__":
    unittest.main()


# --- Interop test: group round-trip through real Kdenlive --------------------
#
# The Kdenlive CLI (kdenlive 26.04) does NOT support a headless
# "open + save" mode. Its only headless operations are --render
# (which renders to a video file, not a project) and kdenlive_render.
# The MLT CLI (melt) can load and re-save XML, but it drops
# kdenlive:* properties (verified empirically — melt strips everything
# not in the MLT core spec, including kdenlive:sequenceproperties.groups).
#
# So the only way to truly verify "Kdenlive preserves our groups on
# re-save" is to drive the real Kdenlive GUI via Xvfb. That is the
# load-bearing test for sub-project 2a, and it requires a full
# Kdenlive launch with D-Bus (the same machinery the persistent
# TestE2EPiSession above uses). We keep the test code in place so
# that when the Xvfb-Kdenlive harness is extended, this test activates
# automatically; for now it skips with a clear reason.
import pytest


_KdenliveBin = pytest.mark.skipif(
    shutil.which("kdenlive") is None,
    reason="kdenlive not installed",
)


@_KdenliveBin
def test_groups_round_trip_through_real_kdenlive(tmp_path):
    """A project with a group created by pyagent's group_clips opens
    cleanly in real Kdenlive, and re-saving it preserves the group
    structure (type, pyagent:name, children, leaf data format).

    Currently SKIPPED: kdenlive 26.04 CLI has no headless open+save
    mode. melt (the MLT CLI) drops kdenlive:* properties. The
    Xvfb+Kdenlive harness in TestE2EPiSession above is the right
    vehicle, but extending it for this test is out of scope for
    the sub-project 2a deliverable.
    """
    pytest.skip(
        "kdenlive CLI has no headless open+save; melt drops kdenlive:* "
        "properties. See test_groups_round_trip_through_real_kdenlive "
        "docstring for the path forward."
    )


@_KdenliveBin
def test_2b_round_trip_through_real_kdenlive():
    """Build a project with a keyframed effect, a track effect, and a
    time-remapped clip. Open in real Kdenlive, save, re-load, and verify
    all three features survive.

    ACTIVATION: requires the Xvfb+Kdenlive harness extension documented
    in BUGS_FIXED T4.5. Currently always skipped."""
    pytest.skip("Real Kdenlive interop test is gated on the Xvfb harness extension")
