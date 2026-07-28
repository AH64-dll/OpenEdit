"""Unit tests for waveform cut inspection image generation (visual_verify.py)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from open_edit.serve import visual_verify  # noqa: E402


# ---------------------------------------------------------------------------
# Unit tests using mocks (deterministic)
# ---------------------------------------------------------------------------

def test_missing_ffmpeg_binary(tmp_path):
    """When shutil.which('ffmpeg') returns None, return error status dict."""
    input_file = tmp_path / "input.mp4"
    input_file.touch()
    output_file = tmp_path / "out.jpg"

    with mock.patch("shutil.which", return_value=None):
        res = visual_verify.generate_waveform_inspection_image(
            input_path=input_file,
            output_path=output_file,
            cut_time_sec=5.0,
        )

    assert res["status"] == "error"
    assert "FFmpeg binary not found" in res["error"]


def test_basic_vstack_composite_command_syntax(tmp_path):
    """Verify vstack command building, timing calculation, and filter structure."""
    input_file = tmp_path / "input.mp4"
    input_file.touch()
    output_file = tmp_path / "out.jpg"

    def fake_which(cmd):
        if cmd == "ffmpeg":
            return "/usr/bin/ffmpeg"
        if cmd == "ffprobe":
            return "/usr/bin/ffprobe"
        return None

    def fake_run(cmd, *args, **kwargs):
        if "ffprobe" in cmd[0]:
            return mock.Mock(returncode=0, stdout="video\naudio\n", stderr="")
        output_file.touch()
        return mock.Mock(returncode=0, stdout="", stderr="")

    with mock.patch("shutil.which", side_effect=fake_which), \
         mock.patch("subprocess.run", side_effect=fake_run) as run_mock:

        res = visual_verify.generate_waveform_inspection_image(
            input_path=input_file,
            output_path=output_file,
            cut_time_sec=10.0,
            window_sec=4.0,
            layout="vstack",
            width=1280,
            height=720,
            colors="cyan|blue",
        )

    assert res["status"] == "ok"
    assert res["output_path"] == str(output_file)
    assert res["cut_time_sec"] == 10.0
    assert res["window_sec"] == 4.0
    assert res["layout"] == "vstack"
    assert res["width"] == 1280
    assert res["height"] == 720

    # Inspect FFmpeg invocation call
    ffmpeg_call = [call for call in run_mock.call_args_list if "ffmpeg" in call.args[0][0]][0]
    cmd = ffmpeg_call.args[0]
    assert ffmpeg_call.kwargs.get("shell") is False
    assert ffmpeg_call.kwargs.get("timeout") == 30

    # Start time = 10.0 - 4.0 / 2 = 8.0
    ss_idx = cmd.index("-ss")
    assert cmd[ss_idx + 1] == "8.0000"
    t_idx = cmd.index("-t")
    assert cmd[t_idx + 1] == "4.0000"

    fc_idx = cmd.index("-filter_complex")
    fc_str = cmd[fc_idx + 1]
    assert "vstack=inputs=2" in fc_str
    assert "showwavespic=s=1280x360:colors=cyan|blue" in fc_str
    assert "drawbox=x=640:y=0:w=2:h=ih:color=red:t=fill" in fc_str


def test_hstack_layout_parameters(tmp_path):
    """Verify hstack layout splits width and produces side-by-side filter."""
    input_file = tmp_path / "input.mp4"
    input_file.touch()
    output_file = tmp_path / "out.jpg"

    def fake_which(cmd):
        return f"/usr/bin/{cmd}"

    def fake_run(cmd, *args, **kwargs):
        if "ffprobe" in cmd[0]:
            return mock.Mock(returncode=0, stdout="video\naudio\n", stderr="")
        output_file.touch()
        return mock.Mock(returncode=0, stdout="", stderr="")

    with mock.patch("shutil.which", side_effect=fake_which), \
         mock.patch("subprocess.run", side_effect=fake_run) as run_mock:

        res = visual_verify.generate_waveform_inspection_image(
            input_path=input_file,
            output_path=output_file,
            cut_time_sec=5.0,
            window_sec=2.0,
            layout="hstack",
            width=1280,
            height=720,
        )

    assert res["status"] == "ok"
    assert res["layout"] == "hstack"

    ffmpeg_call = [call for call in run_mock.call_args_list if "ffmpeg" in call.args[0][0]][0]
    cmd = ffmpeg_call.args[0]
    fc_str = cmd[cmd.index("-filter_complex") + 1]
    assert "hstack=inputs=2" in fc_str
    # Each panel width = 640, height = 720
    assert "showwavespic=s=640x720" in fc_str
    assert "drawbox=x=320:y=0:w=2:h=ih:color=red:t=fill" in fc_str


def test_audio_only_stream_fallback(tmp_path):
    """When input has only audio streams, use synthetic black video panel."""
    input_file = tmp_path / "audio.wav"
    input_file.touch()
    output_file = tmp_path / "out.jpg"

    def fake_which(cmd):
        return f"/usr/bin/{cmd}"

    def fake_run(cmd, *args, **kwargs):
        if "ffprobe" in cmd[0]:
            return mock.Mock(returncode=0, stdout="audio\n", stderr="")
        output_file.touch()
        return mock.Mock(returncode=0, stdout="", stderr="")

    with mock.patch("shutil.which", side_effect=fake_which), \
         mock.patch("subprocess.run", side_effect=fake_run) as run_mock:

        res = visual_verify.generate_waveform_inspection_image(
            input_path=input_file,
            output_path=output_file,
            cut_time_sec=3.0,
            window_sec=2.0,
        )

    assert res["status"] == "ok"
    ffmpeg_call = [call for call in run_mock.call_args_list if "ffmpeg" in call.args[0][0]][0]
    cmd = ffmpeg_call.args[0]
    fc_str = cmd[cmd.index("-filter_complex") + 1]
    assert "color=c=black:s=1280x360" in fc_str
    assert "[0:v]" not in fc_str


def test_silent_video_stream_fallback(tmp_path):
    """When input has only video streams, use synthetic silent audio generator anullsrc."""
    input_file = tmp_path / "silent.mp4"
    input_file.touch()
    output_file = tmp_path / "out.jpg"

    def fake_which(cmd):
        return f"/usr/bin/{cmd}"

    def fake_run(cmd, *args, **kwargs):
        if "ffprobe" in cmd[0]:
            return mock.Mock(returncode=0, stdout="video\n", stderr="")
        output_file.touch()
        return mock.Mock(returncode=0, stdout="", stderr="")

    with mock.patch("shutil.which", side_effect=fake_which), \
         mock.patch("subprocess.run", side_effect=fake_run) as run_mock:

        res = visual_verify.generate_waveform_inspection_image(
            input_path=input_file,
            output_path=output_file,
            cut_time_sec=3.0,
            window_sec=2.0,
        )

    assert res["status"] == "ok"
    ffmpeg_call = [call for call in run_mock.call_args_list if "ffmpeg" in call.args[0][0]][0]
    cmd = ffmpeg_call.args[0]
    fc_str = cmd[cmd.index("-filter_complex") + 1]
    assert "anullsrc=" in fc_str
    assert "[0:a]" not in fc_str


def test_subprocess_timeout_handling(tmp_path):
    """When subprocess times out, return error dict."""
    input_file = tmp_path / "input.mp4"
    input_file.touch()
    output_file = tmp_path / "out.jpg"

    with mock.patch("shutil.which", return_value="/usr/bin/ffmpeg"), \
         mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="ffmpeg", timeout=30)):

        res = visual_verify.generate_waveform_inspection_image(
            input_path=input_file,
            output_path=output_file,
            cut_time_sec=2.0,
        )

    assert res["status"] == "error"
    assert "timed out" in res["error"].lower()


def test_subprocess_error_handling(tmp_path):
    """When subprocess fails with non-zero exit code, return error dict."""
    input_file = tmp_path / "input.mp4"
    input_file.touch()
    output_file = tmp_path / "out.jpg"

    def fake_run(cmd, *args, **kwargs):
        if "ffprobe" in cmd[0]:
            return mock.Mock(returncode=0, stdout="video\naudio\n", stderr="")
        return mock.Mock(returncode=1, stdout="", stderr="Decoder error occurred")

    with mock.patch("shutil.which", return_value="/usr/bin/ffmpeg"), \
         mock.patch("subprocess.run", side_effect=fake_run):

        res = visual_verify.generate_waveform_inspection_image(
            input_path=input_file,
            output_path=output_file,
            cut_time_sec=2.0,
        )

    assert res["status"] == "error"
    assert "Decoder error occurred" in res["error"]


def test_cut_time_near_zero_clamping(tmp_path):
    """When cut_time_sec is 0.5s and window is 2.0s, start_time clamps to 0.0 and cut line ratio is 0.25."""
    input_file = tmp_path / "input.mp4"
    input_file.touch()
    output_file = tmp_path / "out.jpg"

    def fake_which(cmd):
        return f"/usr/bin/{cmd}"

    def fake_run(cmd, *args, **kwargs):
        if "ffprobe" in cmd[0]:
            return mock.Mock(returncode=0, stdout="video\naudio\n", stderr="")
        output_file.touch()
        return mock.Mock(returncode=0, stdout="", stderr="")

    with mock.patch("shutil.which", side_effect=fake_which), \
         mock.patch("subprocess.run", side_effect=fake_run) as run_mock:

        res = visual_verify.generate_waveform_inspection_image(
            input_path=input_file,
            output_path=output_file,
            cut_time_sec=0.5,
            window_sec=2.0,
            width=1000,
            height=500,
        )

    assert res["status"] == "ok"
    ffmpeg_call = [call for call in run_mock.call_args_list if "ffmpeg" in call.args[0][0]][0]
    cmd = ffmpeg_call.args[0]
    ss_idx = cmd.index("-ss")
    assert cmd[ss_idx + 1] == "0.0000"
    # Marker X = 1000 * (0.5 / 2.0) = 250
    fc_str = cmd[cmd.index("-filter_complex") + 1]
    assert "drawbox=x=250:y=0:w=2:h=ih:color=red:t=fill" in fc_str


# ---------------------------------------------------------------------------
# Real FFmpeg integration test (runs if ffmpeg is installed)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg binary required for integration test")
def test_real_ffmpeg_waveform_generation(tmp_path):
    """End-to-end integration test creating a real composite image."""
    media_file = tmp_path / "media.mp4"
    out_file = tmp_path / "waveform_out.jpg"

    # Generate 3-second test clip with audio and video
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=duration=3:size=640x360:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
            "-c:v", "libx264", "-c:a", "aac",
            str(media_file),
        ],
        check=True, capture_output=True, text=True,
    )

    res = visual_verify.generate_waveform_inspection_image(
        input_path=media_file,
        output_path=out_file,
        cut_time_sec=1.5,
        window_sec=2.0,
        layout="vstack",
        width=640,
        height=360,
    )

    assert res["status"] == "ok"
    assert out_file.exists()
    assert out_file.stat().st_size > 0
