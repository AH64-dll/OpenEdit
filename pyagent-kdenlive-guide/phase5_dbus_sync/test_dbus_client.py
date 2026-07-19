import unittest
from unittest import mock
from phase5_dbus_sync.dbus_client import (
    KdenliveDBus, detect_service_name, is_running,
)


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
        self.assertTrue(self.kd.clean_restart(clean=False))
        fake_call.assert_called_once_with("cleanRestart", "b", False)

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

    @mock.patch.object(KdenliveDBus, "_call_with_reply")
    def test_has_scripting_api(self, fake_call_reply):
        fake_call_reply.return_value = (True, ["my_project"])
        self.assertTrue(self.kd.has_scripting_api)
        fake_call_reply.assert_called_with(
            self.kd.path, "org.kde.kdenlive.scripting", "getProjectName", ""
        )

        fake_call_reply.return_value = (False, None)
        self.assertFalse(self.kd.has_scripting_api)

    @mock.patch.object(KdenliveDBus, "_call_with_reply")
    def test_insert_clip_to_track(self, fake_call_reply):
        fake_call_reply.return_value = (True, [])
        self.assertTrue(self.kd.insert_clip_to_track(1, "clip123", 100))
        fake_call_reply.assert_called_once_with(
            self.kd.path,
            "org.kde.kdenlive.scripting",
            "insertTimelineClip",
            "isi",
            1,
            "clip123",
            100,
        )

    @mock.patch.object(KdenliveDBus, "_call_with_reply")
    def test_get_timeline_duration(self, fake_call_reply):
        fake_call_reply.return_value = (True, [1200])
        self.assertEqual(self.kd.get_timeline_duration(), 1200)
        fake_call_reply.assert_called_once_with(
            self.kd.path, "org.kde.kdenlive.scripting", "getTimelineDuration", ""
        )

        fake_call_reply.return_value = (False, None)
        self.assertIsNone(self.kd.get_timeline_duration())


class TestKdenliveProcessDiscovery(unittest.TestCase):
    """Cover `is_running` + `detect_service_name` (moved from
    kdenlive_state.py into dbus_client.py in Task 4.1)."""

    @mock.patch("phase5_dbus_sync.dbus_client.subprocess.run")
    def test_is_running_true(self, fake_run):
        fake_run.return_value = mock.Mock(returncode=0, stdout="12345\n")
        self.assertTrue(is_running())

    @mock.patch("phase5_dbus_sync.dbus_client.subprocess.run")
    def test_is_running_false(self, fake_run):
        fake_run.return_value = mock.Mock(returncode=1, stdout="")
        self.assertFalse(is_running())

    @mock.patch("phase5_dbus_sync.dbus_client.subprocess.run")
    def test_detect_service_name_found(self, fake_run):
        fake_run.return_value = mock.Mock(
            returncode=0,
            stdout="org.kde.kdenlive-2046260  …\norg.freedesktop.systemd1 …\n",
        )
        self.assertEqual(detect_service_name(), "org.kde.kdenlive-2046260")

    @mock.patch("phase5_dbus_sync.dbus_client.subprocess.run")
    def test_detect_service_name_none(self, fake_run):
        fake_run.return_value = mock.Mock(returncode=0, stdout="")
        self.assertIsNone(detect_service_name())
