"""Tests for session state transitions."""
import time
import unittest

from phase4_chat_ui.session import Session
from phase4_chat_ui.types import ChatMessage, PlanCard


class TestSession(unittest.TestCase):
    def setUp(self):
        self.s = Session()

    def test_add_user_message(self):
        self.s.add_user_message("cut the clip")
        self.assertEqual(len(self.s.history), 1)
        m = self.s.history[0]
        self.assertEqual(m.role, "user")
        self.assertEqual(m.content, "cut the clip")
        self.assertIsInstance(m.timestamp, float)

    def test_add_assistant_message(self):
        self.s.add_assistant_message("done")
        self.assertEqual(self.s.history[-1].role, "assistant")

    def test_add_tool_event(self):
        self.s.add_tool_event("pyagent_append_clip",
                              {"track_index": 0}, {"clip_id": "c1"})
        m = self.s.history[-1]
        self.assertEqual(m.role, "tool")
        self.assertEqual(m.tool_name, "pyagent_append_clip")
        self.assertIn("clip_id", m.content)

    def test_pending_plan_set_and_resolve(self):
        plan = PlanCard(plan_id="p1", summary="append clip", diff="+ clip")
        self.s.set_pending_plan(plan)
        self.assertIsNotNone(self.s.pending_plan)
        self.assertEqual(self.s.pending_plan.status, "pending")
        self.s.resolve_plan("approved")
        self.assertEqual(self.s.pending_plan.status, "approved")
        self.s.clear_pending_plan()
        self.assertIsNone(self.s.pending_plan)

    def test_resolve_without_plan_is_noop(self):
        self.s.resolve_plan("approved")  # should not raise
        self.assertIsNone(self.s.pending_plan)

    def test_history_dicts_roundtrip(self):
        self.s.add_user_message("hi")
        self.s.add_assistant_message("hello")
        d = self.s.history_dicts()
        self.assertEqual(len(d), 2)
        self.assertEqual(d[0]["role"], "user")
        self.assertEqual(d[0]["content"], "hi")

    def test_set_project_state(self):
        self.s.set_project_state({"fps": 30, "width": 1920})
        self.assertEqual(self.s.last_project_state["fps"], 30)

    def test_session_serialization(self):
        s1 = Session(session_id="test-session-123", name="Test Session", project="/path/to/project.kdenlive")
        s1.add_user_message("hello", ["data:image/png;base64,123"])
        s1.add_assistant_message("world")
        plan = PlanCard(plan_id="p1", summary="summary", diff="diff")
        s1.set_pending_plan(plan)
        
        d = s1.to_dict()
        self.assertEqual(d["session_id"], "test-session-123")
        self.assertEqual(d["name"], "Test Session")
        self.assertEqual(d["project"], "/path/to/project.kdenlive")
        self.assertEqual(len(d["history"]), 2)
        self.assertEqual(d["history"][0]["images"], [])
        self.assertEqual(d["pending_plan"]["plan_id"], "p1")
        
        s2 = Session.from_dict(d)
        self.assertEqual(s2.session_id, "test-session-123")
        self.assertEqual(s2.name, "Test Session")
        self.assertEqual(s2.project, "/path/to/project.kdenlive")
        self.assertEqual(len(s2.history), 2)
        self.assertEqual(s2.history[0].images, [])
        self.assertEqual(s2.pending_plan.plan_id, "p1")

    def test_session_persistence(self):
        import os
        from phase4_chat_ui.session import get_sessions_dir, list_sessions
        
        s = Session(session_id="test-persist-999", name="Persist Test", project="/path/to/persist.kdenlive")
        s.add_user_message("persistent message")
        s.save()
        
        # Test loading
        loaded = Session.load("test-persist-999")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.name, "Persist Test")
        self.assertEqual(len(loaded.history), 1)
        self.assertEqual(loaded.history[0].content, "persistent message")
        
        # Test list_sessions
        sessions = list_sessions()
        session_ids = [item["session_id"] for item in sessions]
        self.assertIn("test-persist-999", session_ids)
        
        # Cleanup
        path = get_sessions_dir() / "test-persist-999.json"
        if path.exists():
            os.remove(path)

    def test_session_id_validation(self):
        # Invalid session ID in load
        self.assertIsNone(Session.load("../../etc/passwd"))
        self.assertIsNone(Session.load("abc/def"))
        self.assertIsNone(Session.load("abc$def"))

        # Invalid session ID in save should not write files
        from phase4_chat_ui.session import get_sessions_dir
        s = Session(session_id="invalid/session/id")
        s.save()
        path = get_sessions_dir() / "invalid/session/id.json"
        self.assertFalse(path.exists())

    def test_history_cap(self):
        s = Session(session_id="test-cap")
        for i in range(550):
            s.add_user_message(f"msg {i}")
        self.assertEqual(len(s.history), 500)
        self.assertEqual(s.history[0].content, "msg 50")
        self.assertEqual(s.history[-1].content, "msg 549")


if __name__ == "__main__":
    unittest.main()
