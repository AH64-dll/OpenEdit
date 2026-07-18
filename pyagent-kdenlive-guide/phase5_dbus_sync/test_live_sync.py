import unittest
from unittest import mock
from phase5_dbus_sync.live_sync import LiveSync, LIVE_CAPABLE, RELOAD_AFTER


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
        self.assertEqual(r["mode"], "file")
        fake_dbus.add_project_clip.assert_not_called()

    @mock.patch("phase5_dbus_sync.live_sync.detect_service_name")
    @mock.patch("phase5_dbus_sync.live_sync.run_op")
    def test_apply_file_mode_auto_reloads(self, fake_run_op, fake_detect):
        # A file-mode op must attempt a guarded reload so the edit shows.
        fake_run_op.return_value = (0, {"ok": True})
        fake_detect.return_value = "org.kde.kdenlive-1"
        fake_dbus = mock.Mock()
        fake_dbus.available = True
        fake_dbus.clean_restart.return_value = True
        ls = LiveSync("/tmp/x.kdenlive", dbus=fake_dbus, notifier=mock.Mock())
        r = ls.apply("pyagent_add_transition", {"duration_sec": 1.0})
        self.assertEqual(r["mode"], "file")
        fake_run_op.assert_called_once()
        fake_dbus.clean_restart.assert_called_once_with(clean=False)

    @mock.patch("phase5_dbus_sync.live_sync.detect_service_name")
    @mock.patch("phase5_dbus_sync.live_sync.run_op")
    @mock.patch("subprocess.Popen")
    def test_apply_reloads_and_relaunch_on_crash(
        self, fake_popen, fake_run_op, fake_detect
    ):
        # If cleanRestart crashes Kdenlive, we must relaunch it on the
        # (now-updated) project so the user keeps a live window.
        fake_run_op.return_value = (0, {"ok": True})
        fake_detect.return_value = "org.kde.kdenlive-1"
        fake_dbus = mock.Mock()
        fake_dbus.available = True
        fake_dbus.clean_restart.return_value = True
        ls = LiveSync("/tmp/x.kdenlive", dbus=fake_dbus, notifier=mock.Mock())
        # Simulate: cleanRestart was attempted, then kdenlive is gone.
        ls._dbus.available = False
        ls._relaunch_kdenlive()
        fake_popen.assert_called_once()
        args, kwargs = fake_popen.call_args
        self.assertEqual(args[0][0], "kdenlive")
        self.assertEqual(args[0][1], "/tmp/x.kdenlive")


if __name__ == "__main__":
    unittest.main()
