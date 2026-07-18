import unittest
from unittest import mock
from phase5_dbus_sync.live_sync import LiveSync, LIVE_CAPABLE


class TestLiveSync(unittest.TestCase):
    def test_live_capable_set(self):
        self.assertIn("pyagent_import_media", LIVE_CAPABLE)
        self.assertIn("pyagent_append_clip", LIVE_CAPABLE)
        self.assertIn("pyagent_apply_effect", LIVE_CAPABLE)
        self.assertNotIn("pyagent_add_transition", LIVE_CAPABLE)

    @mock.patch("phase5_dbus_sync.live_sync.detect_service_name")
    def test_is_live_false_when_no_dbus(self, fake_detect):
        # Force "no running Kdenlive" so the test is deterministic even
        # when a real instance happens to be open on the machine.
        fake_detect.return_value = None
        ls = LiveSync("/tmp/x.kdenlive", dbus=None)
        self.assertFalse(ls.is_live("pyagent_import_media"))

    def test_is_live_true_with_available_dbus(self):
        fake_dbus = mock.Mock()
        fake_dbus.available = True
        ls = LiveSync("/tmp/x.kdenlive", dbus=fake_dbus)
        self.assertTrue(ls.is_live("pyagent_import_media"))

    @mock.patch("phase5_dbus_sync.live_sync.detect_service_name")
    def test_apply_live_import(self, fake_detect):
        fake_detect.return_value = "org.kde.kdenlive-1"
        fake_dbus = mock.Mock()
        fake_dbus.available = True
        fake_dbus.add_project_clip.return_value = True
        ls = LiveSync("/tmp/x.kdenlive", dbus=fake_dbus)
        r = ls.apply("pyagent_import_media", {"path": "/clip.mp4"})
        self.assertEqual(r["mode"], "live")
        fake_dbus.add_project_clip.assert_called_once_with("/clip.mp4")

    @mock.patch("phase5_dbus_sync.live_sync.detect_service_name")
    @mock.patch("phase5_dbus_sync.live_sync.run_op")
    def test_apply_falls_back_to_file(self, fake_run_op, fake_detect):
        fake_detect.return_value = None  # no running Kdenlive
        fake_run_op.return_value = (0, {"ok": True})
        ls = LiveSync("/tmp/x.kdenlive", dbus=None)
        r = ls.apply("pyagent_add_transition", {"duration_sec": 1.0})
        self.assertEqual(r["mode"], "file")
        fake_run_op.assert_called_once()

    @mock.patch("phase5_dbus_sync.live_sync.detect_service_name")
    @mock.patch("phase5_dbus_sync.live_sync.run_op")
    @mock.patch("phase5_dbus_sync.live_sync.notify")
    def test_apply_live_no_reload(self, fake_notify, fake_run_op, fake_detect):
        # A live-capable op that succeeds live must NOT trigger a reload.
        fake_detect.return_value = "org.kde.kdenlive-1"
        fake_dbus = mock.Mock()
        fake_dbus.available = True
        fake_dbus.add_project_clip.return_value = True
        ls = LiveSync("/tmp/x.kdenlive", dbus=fake_dbus)
        r = ls.apply("pyagent_import_media", {"path": "/clip.mp4"})
        self.assertEqual(r["mode"], "live")
        fake_dbus.clean_restart.assert_not_called()

    @mock.patch("phase5_dbus_sync.live_sync.detect_service_name")
    @mock.patch("phase5_dbus_sync.live_sync.run_op")
    @mock.patch("phase5_dbus_sync.live_sync.notify")
    def test_apply_file_mode_auto_reloads(self, fake_notify, fake_run_op, fake_detect):
        # A file-mode op must reload the open Kdenlive so the edit shows live.
        fake_run_op.return_value = (0, {"ok": True})
        fake_detect.return_value = "org.kde.kdenlive-1"
        fake_dbus = mock.Mock()
        fake_dbus.available = True
        ls = LiveSync("/tmp/x.kdenlive", dbus=fake_dbus, notifier=fake_notify)
        r = ls.apply("pyagent_add_transition", {"duration_sec": 1.0})
        self.assertEqual(r["mode"], "file")
        fake_run_op.assert_called_once()
        fake_dbus.clean_restart.assert_called_once_with(clean=False)
        fake_notify.assert_called_once()


if __name__ == "__main__":
    unittest.main()
