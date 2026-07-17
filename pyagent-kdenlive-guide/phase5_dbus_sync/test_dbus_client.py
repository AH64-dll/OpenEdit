import unittest
from unittest import mock
from phase5_dbus_sync.dbus_client import KdenliveDBus


class FakeMessage:
    def __init__(self, body=None):
        self.body = body or []


class TestKdenliveDBus(unittest.TestCase):
    def setUp(self):
        self.kd = KdenliveDBus()

    @mock.patch("phase5_dbus_sync.dbus_client.open_dbus_connection")
    def test_available_true(self, fake_open):
        fake_open.return_value = mock.Mock()
        self.assertTrue(self.kd.available)

    @mock.patch("phase5_dbus_sync.dbus_client.open_dbus_connection")
    def test_available_false_on_error(self, fake_open):
        fake_open.side_effect = Exception("no bus")
        self.assertFalse(self.kd.available)

    @mock.patch.object(KdenliveDBus, "_call")
    def test_add_project_clip(self, fake_call):
        fake_call.return_value = True
        self.assertTrue(self.kd.add_project_clip("/x.mp4"))
        fake_call.assert_called_once_with("addProjectClip", "ss", "/x.mp4", "")

    @mock.patch.object(KdenliveDBus, "_call")
    def test_add_timeline_clip(self, fake_call):
        fake_call.return_value = True
        self.assertTrue(self.kd.add_timeline_clip("/x.mp4"))
        fake_call.assert_called_once_with("addTimelineClip", "s", "/x.mp4")

    @mock.patch.object(KdenliveDBus, "_call")
    def test_add_effect(self, fake_call):
        fake_call.return_value = True
        self.assertTrue(self.kd.add_effect("crop"))
        fake_call.assert_called_once_with("addEffect", "s", "crop")

    @mock.patch.object(KdenliveDBus, "_call")
    def test_clean_restart(self, fake_call):
        fake_call.return_value = True
        self.assertTrue(self.kd.clean_restart(clean=False, force_quit=True))
        fake_call.assert_called_once_with("cleanRestart", "bb", False, True)

    @mock.patch.object(KdenliveDBus, "_call")
    def test_call_false_on_exception(self, fake_call):
        # _call returns False when the underlying D-Bus call fails; the public
        # methods propagate that as a falsy result.
        fake_call.return_value = False
        self.assertFalse(self.kd.add_project_clip("/x.mp4"))

    @mock.patch.object(KdenliveDBus, "_call")
    def test_exit_app(self, fake_call):
        fake_call.return_value = True
        self.assertTrue(self.kd.exit_app())
        fake_call.assert_called_once_with("exitApp", "")
