"""Phase 4.5 W1: transcription wrapper."""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


def test_transcribe_returns_empty_without_whisper():
    from open_edit.storage.transcription import transcribe, _has_whisper
    with patch("open_edit.storage.transcription._has_whisper", return_value=False):
        result = transcribe(Path("/tmp/fake.mp4"))
    assert result == []


def test_transcribe_with_mocked_whisper(tmp_path):
    from open_edit.storage.transcription import transcribe
    fake_segment = MagicMock()
    fake_segment.words = [
        MagicMock(word="hello", start=0.0, end=0.5, probability=0.99),
        MagicMock(word="world", start=0.5, end=1.0, probability=0.98),
    ]
    fake_model = MagicMock()
    fake_model.transcribe.return_value = ([fake_segment], MagicMock(language="en"))
    with patch("open_edit.storage.transcription._has_whisper", return_value=True), \
         patch("open_edit.storage.transcription.WhisperModel", return_value=fake_model):
        result = transcribe(tmp_path / "test.mp4", model_size="base")
    assert len(result) == 2
    assert result[0].word == "hello"
    assert result[0].t_start == 0.0


def test_transcribe_returns_empty_on_internal_failure(tmp_path, caplog):
    """M1: one bad file must not break the batch — transcribe() returns []."""
    from open_edit.storage.transcription import transcribe
    fake_model = MagicMock()
    fake_model.transcribe.side_effect = RuntimeError("whisper blew up")
    with patch("open_edit.storage.transcription._has_whisper", return_value=True), \
         patch("open_edit.storage.transcription.WhisperModel", return_value=fake_model), \
         caplog.at_level("WARNING"):
        result = transcribe(tmp_path / "broken.mp4", model_size="base")
    assert result == []
