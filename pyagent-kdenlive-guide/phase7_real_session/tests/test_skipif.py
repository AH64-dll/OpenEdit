"""Unit tests for skipif_helpers."""
from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest import mock

from phase7_real_session.skipif_helpers import (
    _has,
    _has_opencode_auth,
    _kdenlive_already_on_bus,
)


class TestHas(unittest.TestCase):
    def test_returns_true_for_existing_binary(self) -> None:
        # `python3` is always on PATH on this machine.
        self.assertTrue(_has("python3"))

    def test_returns_false_for_missing_binary(self) -> None:
        self.assertFalse(_has("definitely-not-a-binary-xyz"))


class TestHasOpencodeAuth(unittest.TestCase):
    def test_true_when_env_var_set(self) -> None:
        with mock.patch.dict(os.environ, {"OPENCODE_API_KEY": "x"}, clear=False):
            self.assertTrue(_has_opencode_auth())

    def test_true_when_auth_file_exists(self) -> None:
        fake_auth = Path.home() / ".pi/agent/auth.json"
        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch.object(Path, "is_file", return_value=True), \
             mock.patch.object(Path, "__truediv__", lambda *a: fake_auth):
            self.assertTrue(_has_opencode_auth())

    def test_false_when_neither(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch.object(Path, "is_file", return_value=False):
            self.assertFalse(_has_opencode_auth())


class TestKdenliveAlreadyOnBus(unittest.TestCase):
    def test_true_when_kdenlive_in_list(self) -> None:
        fake = mock.Mock()
        fake.stdout = "string \"org.kde.kdenlive\"\n"
        with mock.patch("subprocess.run", return_value=fake):
            self.assertTrue(_kdenlive_already_on_bus())

    def test_false_when_no_kdenlive(self) -> None:
        fake = mock.Mock()
        fake.stdout = "string \"org.freedesktop.DBus\"\n"
        with mock.patch("subprocess.run", return_value=fake):
            self.assertFalse(_kdenlive_already_on_bus())

    def test_false_when_dbus_send_fails(self) -> None:
        fake = mock.Mock()
        fake.stdout = ""
        fake.returncode = 1
        with mock.patch("subprocess.run", return_value=fake):
            self.assertFalse(_kdenlive_already_on_bus())


if __name__ == "__main__":
    unittest.main()
