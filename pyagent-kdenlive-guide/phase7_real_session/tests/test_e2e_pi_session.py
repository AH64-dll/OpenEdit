"""Real pi-session end-to-end test.

Drives a real pi session against a real Kdenlive via the chat UI,
then asserts:

1. pi called pyagent_add_transition (the edit was actually made).
2. The tool's result text is non-error (pi 0.80+ forwards tool
   output as `content`, not a bare result dict, so we check the
   text rather than result.ok).
3. The project file changed on disk after the live-sync settled:
   a <transition> appeared, and its mlt_service matches a
   dissolve/crossfade (real Kdenlive persists a Dissolve as
   mlt_service="luma", resolved from the catalog).
4. The LLM described the action in its final message.

Note on non-determinism: this test drives a *live* LLM (pi ->
provider). The model may occasionally stop and ask for
clarification instead of running the tool chain, so the test can
flake. It is intended as a manual real-session smoke test
(`make -C phase7_real_session test-e2e`), not a hard CI gate. The
deterministic unit/integration suites cover correctness; this one
proves the whole stack actually works end-to-end on a real machine.

Note on assertion 3: the original spec called for a live D-Bus read
of the running Kdenlive's timeline. KdenliveDBus (phase5) is
write-only (no get_transition_list()). read_timeline_state() in
dbus_probe therefore parses the project file, which is the source
of truth. A short sleep after the tool returns gives the live-sync
time to settle.

Skipped cleanly on machines missing the required deps.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from phase7_real_session.skipif_helpers import (
    _has,
    _has_opencode_auth,
    _kdenlive_already_on_bus,
)
from phase7_real_session.xvfb import XvfbContext
from phase7_real_session.kdenlive import KdenliveLaunch
from phase7_real_session.chat_ui import ChatUIServer
from phase7_real_session.ws_client import WSClient
from phase7_real_session.dbus_probe import read_timeline_state

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
        # Read the pre-run XML so we can diff later.
        self._pre_xml = self.project.read_text()
        # Track resources for cleanup.
        self._xvfb: XvfbContext | None = None
        self._kdenlive: KdenliveLaunch | None = None
        self._chat_ui: ChatUIServer | None = None
        self._events: list[dict] = []
        self._transcript_path = self.tmp / "transcript.json"
        # Set PYAGENT_KEEP_E2E_TMP=1 in the env to preserve the
        # tempdir on teardown for post-mortem inspection. Off by
        # default so the test doesn't litter /tmp.
        self._keep_tmp = bool(os.environ.get("PYAGENT_KEEP_E2E_TMP"))

    def tearDown(self) -> None:
        # Cleanup order: Kdenlive -> chat UI -> Xvfb.
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
        """Return (tool_event, args) for the add_transition call, if any."""
        for ev in self._events:
            if ev.get("type") == "tool" and ev.get("tool") == "pyagent_add_transition":
                return ev, ev.get("args") or {}
        return None, None

    def _count_transitions_in_file(self) -> int:
        """Count <transition> elements in the tempdir project file."""
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
        """mlt_service values that count as a dissolve/crossfade in Kdenlive.

        The catalog's 'dissolve' entry maps to mlt_service='luma' (Kdenlive's
        luma-wipe = dissolve). We accept that plus the frei0r dissolve filter.
        """
        services = {"luma", "frei0r.dissolve"}
        # The chat UI resolves its catalog from phase1_knowledge_base by
        # default; load it to pick up the real mlt_service for dissolve.
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
        # Step 3: start Xvfb.
        _step("starting Xvfb")
        self._xvfb = XvfbContext(min_display=99, max_display=199)
        display = self._xvfb.__enter__()
        os.environ["DISPLAY"] = display
        _step(f"Xvfb on {display}")

        try:
            # Step 4: start Kdenlive and wait for D-Bus.
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

            # Step 5: start chat UI.
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

            # Step 6+7+8: drive the WebSocket.
            _step("sending prompt via WebSocket")
            ws = WSClient(url=f"{self._chat_ui.url.replace('http', 'ws', 1)}/ws",
                          timeout=180.0)
            self._events = ws.run_prompt_sync(PROMPT)
            _step(f"collected {len(self._events)} events")

            # Save the transcript for debugging.
            self._transcript_path.write_text(json.dumps(self._events, indent=2))

            # Step 9: assertions.
            _step("asserting tool call")
            tool_event, args = self._find_add_transition()
            self.assertIsNotNone(
                tool_event,
                f"pi did not call pyagent_add_transition. "
                f"Events: {[e.get('type') for e in self._events]}. "
                f"Transcript: {self._transcript_path}",
            )

            _step("asserting tool result")
            # pi 0.80+ surfaces tool output in `content` (a list of
            # {type:"text", text:...}); the bare result dict is not
            # forwarded. Extract the text to assert on.
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
            # tool call returns. The chat UI's notifier fires
            # addTimelineClip via D-Bus; Kdenlive updates internally
            # and writes the file back (or holds in memory until next
            # save). After this sleep, the project file is
            # authoritative for both "file changed" and "the kind
            # is dissolve/crossfade" — see module docstring.
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
            # Real Kdenlive persists a Dissolve as mlt_service="luma"
            # (or "frei0r.dissolve"), not the literal string "dissolve".
            # Resolve the catalog's dissolve entry to its true mlt_service.
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
            # On failure, dump the transcript and Kdenlive stderr.
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
