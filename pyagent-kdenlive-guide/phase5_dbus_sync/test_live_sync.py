import unittest
from unittest import mock
from phase5_dbus_sync.live_sync import (
    LIVE_CAPABLE, RELOAD_AFTER, LiveResult, LiveSync, apply, notify,
)


class TestLiveSync(unittest.TestCase):
    def test_live_capable_set_empty(self):
        # On the Kdenlive 26.04 build we target, the D-Bus live methods
        # (addProjectClip/addTimelineClip/cleanRestart) crash the running
        # instance. So LIVE_CAPABLE is intentionally empty and every
        # mutating op goes through the file backend + a safe reload.
        self.assertEqual(len(LIVE_CAPABLE), 0)

    def test_reload_after_covers_all_mutating(self):
        for t in (
            "pyagent_import_media", "pyagent_insert_clip",
            "pyagent_append_clip", "pyagent_move_clip",
            "pyagent_trim_clip", "pyagent_delete_clip",
            "pyagent_add_transition", "pyagent_apply_effect",
            "pyagent_add_marker", "pyagent_save_project",
        ):
            self.assertIn(t, RELOAD_AFTER)

    def test_is_live_always_false(self):
        # No tool is live-capable now, so is_live is always False.
        fake_dbus = mock.Mock()
        fake_dbus.available = True
        ls = LiveSync("/tmp/x.kdenlive", dbus=fake_dbus)
        self.assertFalse(ls.is_live("pyagent_import_media"))
        self.assertFalse(ls.is_live("pyagent_append_clip"))

    @mock.patch("phase5_dbus_sync.live_sync.detect_service_name")
    @mock.patch("phase5_dbus_sync.live_sync.run_op")
    def test_apply_all_ops_go_file_mode(self, fake_run_op, fake_detect):
        fake_detect.return_value = "org.kde.kdenlive-1"
        fake_dbus = mock.Mock()
        fake_dbus.available = True
        fake_run_op.return_value = (0, {"ok": True})
        ls = LiveSync("/tmp/x.kdenlive", dbus=fake_dbus)
        # Even "live-capable" tools now take the file path.
        r = ls.apply("pyagent_import_media", {"paths": ["/clip.mp4"]})
        self.assertIsInstance(r, LiveResult)
        self.assertEqual(r.mode, "file")
        fake_dbus.add_project_clip.assert_not_called()

    @mock.patch("phase5_dbus_sync.live_sync.detect_service_name")
    @mock.patch("phase5_dbus_sync.live_sync.run_op")
    def test_apply_file_mode_notifies(self, fake_run_op, fake_detect):
        # A file-mode op must run the backend and notify the user to reload
        # (we deliberately do NOT call D-Bus cleanRestart on Kdenlive 26.04
        # because it crashes the running instance).
        fake_run_op.return_value = (0, {"ok": True})
        fake_detect.return_value = "org.kde.kdenlive-1"
        fake_dbus = mock.Mock()
        fake_dbus.available = True
        fake_notifier = mock.Mock()
        ls = LiveSync("/tmp/x.kdenlive", dbus=fake_dbus, notifier=fake_notifier)
        r = ls.apply("pyagent_add_transition", {"duration_sec": 1.0})
        self.assertEqual(r.mode, "file")
        fake_run_op.assert_called_once()
        # No D-Bus reload call — it crashes 26.04.
        fake_dbus.clean_restart.assert_not_called()
        # User is told to reload instead.
        fake_notifier.assert_called_once()

    @mock.patch("phase5_dbus_sync.live_sync.detect_service_name")
    @mock.patch("phase5_dbus_sync.live_sync.run_op")
    def test_apply_file_quits_kdenlive_before_writing(self, fake_run_op, fake_detect):
        # Root cause: Kdenlive overwrites the file on save/close, clobbering
        # our edits. The fix: quit Kdenlive BEFORE writing the file.
        fake_run_op.return_value = (0, {"ok": True})
        fake_detect.return_value = "org.kde.kdenlive-1"
        fake_dbus = mock.Mock()
        # `available` is checked twice: first to decide whether to quit,
        # then in a loop to confirm Kdenlive died. Simulate: True initially,
        # then False after exit_app is called.
        avail_calls = [True, False]
        fake_dbus.available = mock.PropertyMock(
            side_effect=lambda: avail_calls.pop(0) if avail_calls else False,
        )
        fake_dbus.exit_app.return_value = True
        ls = LiveSync("/tmp/x.kdenlive", dbus=fake_dbus, notifier=mock.Mock())
        ls.apply("pyagent_add_transition", {"duration_sec": 1.0})
        # exit_app must have been called (Kdenlive quit before file write)
        fake_dbus.exit_app.assert_called()
        # And the file backend was then called
        fake_run_op.assert_called_once()

    @mock.patch("phase5_dbus_sync.live_sync.detect_service_name")
    def test_apply_dbus_success_does_not_quit(self, fake_detect):
        # Bug fix: if the D-Bus live path succeeds, Kdenlive is already
        # in sync with our edit, so we must NOT quit it. The quit only
        # belongs in the file-fallback branch.
        fake_detect.return_value = "org.kde.kdenlive-1"
        fake_dbus = mock.Mock()
        fake_dbus.available = True
        # Pretend a tool IS live-capable and the D-Bus call succeeds.
        with mock.patch.object(LiveSync, "is_live", return_value=True), \
             mock.patch.object(LiveSync, "_apply_via_dbus", return_value=True), \
             mock.patch.object(LiveSync, "_apply_via_file") as fake_file, \
             mock.patch.object(LiveSync, "_quit_kdenlive_if_running") as fake_quit:
            fake_file.return_value = LiveResult(ok=True, mode="file")
            ls = LiveSync("/tmp/x.kdenlive", dbus=fake_dbus, notifier=mock.Mock())
            r = ls.apply("pyagent_import_media", {"paths": ["/clip.mp4"]})
        self.assertEqual(r.mode, "live")
        # The file backend and the quit must NOT have been called.
        fake_file.assert_not_called()
        fake_quit.assert_not_called()

    def test_module_level_apply_returns_dict(self):
        # The public `apply()` entry point is a thin wrapper that returns
        # a plain dict (so `json.dumps` works without asdict() in callers).
        with mock.patch.object(LiveSync, "apply",
                               return_value=LiveResult(ok=True, mode="file",
                                                       result={"x": 1})):
            r = apply("pyagent_save_project", {}, "/tmp/x.kdenlive",
                      notifier=mock.Mock())
        self.assertIsInstance(r, dict)
        self.assertTrue(r["ok"])
        self.assertEqual(r["mode"], "file")
        self.assertEqual(r["result"], {"x": 1})


class TestNotify(unittest.TestCase):
    """Cover the inlined `notify()` helper (moved from notifier.py)."""

    @mock.patch("phase5_dbus_sync.live_sync.shutil.which")
    @mock.patch("phase5_dbus_sync.live_sync.subprocess.run")
    def test_notify_calls_send(self, fake_run, fake_which):
        fake_which.return_value = "/usr/bin/notify-send"
        notify("Title", "Body")
        fake_run.assert_called_once()
        args = fake_run.call_args[0][0]
        self.assertIn("notify-send", args)
        self.assertIn("Title", args)
        self.assertIn("Body", args)

    @mock.patch("phase5_dbus_sync.live_sync.shutil.which")
    @mock.patch("phase5_dbus_sync.live_sync.subprocess.run")
    def test_notify_noop_if_missing(self, fake_run, fake_which):
        fake_which.return_value = None
        notify("Title", "Body")
        fake_run.assert_not_called()

    @mock.patch("phase5_dbus_sync.live_sync.shutil.which")
    @mock.patch("phase5_dbus_sync.live_sync.subprocess.run")
    def test_notify_swallows_errors(self, fake_run, fake_which):
        fake_which.return_value = "/usr/bin/notify-send"
        fake_run.side_effect = Exception("boom")
        notify("Title", "Body")  # must not raise


if __name__ == "__main__":
    unittest.main()
