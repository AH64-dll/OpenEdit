"""Phase 4.5 W1: transcription wrapper."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from open_edit.storage.transcription import transcribe, _has_whisper


class TestTranscription(unittest.TestCase):
    """Unit tests for transcription wrapper."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_transcribe_returns_empty_without_whisper(self) -> None:
        with patch("open_edit.storage.transcription._has_whisper", return_value=False):
            result = transcribe(Path("/tmp/fake.mp4"))
        self.assertEqual(result, [])

    def test_transcribe_with_mocked_whisper(self) -> None:
        fake_segment = MagicMock()
        fake_segment.words = [
            MagicMock(word="hello", start=0.0, end=0.5, probability=0.99),
            MagicMock(word="world", start=0.5, end=1.0, probability=0.98),
        ]
        fake_model = MagicMock()
        fake_model.transcribe.return_value = ([fake_segment], MagicMock(language="en"))
        with patch("open_edit.storage.transcription._has_whisper", return_value=True), \
             patch("open_edit.storage.transcription.WhisperModel", return_value=fake_model):
            result = transcribe(self.tmp_path / "test.mp4", model_size="base")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].word, "hello")
        self.assertEqual(result[0].t_start, 0.0)

    def test_transcribe_returns_empty_on_internal_failure(self) -> None:
        fake_model = MagicMock()
        fake_model.transcribe.side_effect = RuntimeError("whisper blew up")
        with patch("open_edit.storage.transcription._has_whisper", return_value=True), \
             patch("open_edit.storage.transcription.WhisperModel", return_value=fake_model):
            result = transcribe(self.tmp_path / "broken.mp4", model_size="base")
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
