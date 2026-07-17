import unittest
from unittest import mock
from phase5_dbus_sync.notifier import notify


class TestNotifier(unittest.TestCase):
    @mock.patch("phase5_dbus_sync.notifier.shutil.which")
    @mock.patch("phase5_dbus_sync.notifier.subprocess.run")
    def test_notify_calls_send(self, fake_run, fake_which):
        fake_which.return_value = "/usr/bin/notify-send"
        notify("Title", "Body", "normal")
        fake_run.assert_called_once()
        args = fake_run.call_args[0][0]
        self.assertIn("notify-send", args)
        self.assertIn("Title", args)
        self.assertIn("Body", args)

    @mock.patch("phase5_dbus_sync.notifier.shutil.which")
    @mock.patch("phase5_dbus_sync.notifier.subprocess.run")
    def test_notify_noop_if_missing(self, fake_run, fake_which):
        fake_which.return_value = None
        notify("Title", "Body")  # should not raise
        fake_run.assert_not_called()

    @mock.patch("phase5_dbus_sync.notifier.shutil.which")
    @mock.patch("phase5_dbus_sync.notifier.subprocess.run")
    def test_notify_swallows_errors(self, fake_run, fake_which):
        fake_which.return_value = "/usr/bin/notify-send"
        fake_run.side_effect = Exception("boom")
        notify("Title", "Body")  # should not raise


if __name__ == "__main__":
    unittest.main()
