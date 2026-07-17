"""Tests for session state transitions."""
import time
import unittest

from phase4_chat_ui.session import ChatMessage, PlanCard, Session


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


if __name__ == "__main__":
    unittest.main()
