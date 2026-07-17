import unittest
from unittest import mock
from phase5_dbus_sync.kdenlive_state import is_running, detect_service_name


class TestKdenliveState(unittest.TestCase):
    @mock.patch("phase5_dbus_sync.kdenlive_state.subprocess.run")
    def test_is_running_true(self, fake_run):
        fake_run.return_value = mock.Mock(returncode=0, stdout="12345\n")
        self.assertTrue(is_running())

    @mock.patch("phase5_dbus_sync.kdenlive_state.subprocess.run")
    def test_is_running_false(self, fake_run):
        fake_run.return_value = mock.Mock(returncode=1, stdout="")
        self.assertFalse(is_running())

    @mock.patch("phase5_dbus_sync.kdenlive_state.subprocess.run")
    def test_detect_service_name_found(self, fake_run):
        fake_run.return_value = mock.Mock(
            returncode=0,
            stdout="org.kde.kdenlive-2046260  …\norg.freedesktop.systemd1 …\n",
        )
        self.assertEqual(detect_service_name(), "org.kde.kdenlive-2046260")

    @mock.patch("phase5_dbus_sync.kdenlive_state.subprocess.run")
    def test_detect_service_name_none(self, fake_run):
        fake_run.return_value = mock.Mock(returncode=0, stdout="")
        self.assertIsNone(detect_service_name())


if __name__ == "__main__":
    unittest.main()
