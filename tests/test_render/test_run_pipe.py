"""run_pipe: concurrent melt->ffmpeg execution with fake binaries."""
import shutil
import subprocess
import sys
from types import SimpleNamespace
import wave
from pathlib import Path

import pytest

from open_edit.render.melt_runner import PipeRunError, run_pipe
from open_edit.render.encoder import select_encoder
from open_edit.render.pipe_builder import PipeCommands, build_pipe_commands
from open_edit.render.profiles import select_profile
from open_edit.render.remotion.frame_feeder import FrameOverlaySpec


def _fake_melt(path: Path, kind: str) -> Path:
    # fake melt: streams 10 raw frames to stdout (kind=video) or writes a
    # wav (kind=audio); kind=fail exits 1 after writing an error line.
    script = f"""#!/usr/bin/env python3
import sys
kind = {kind!r}
if kind == "video":
    sys.stdout.buffer.write(b"\\x00" * (1280 * 720 * 3 // 2))  # one 720p frame
    for _ in range(9):
        sys.stdout.buffer.write(b"\\x00" * (1280 * 720 * 3 // 2))
elif kind == "fail":
    sys.stderr.write("fake melt exploded\\n")
    sys.exit(1)
else:
    wav = next(a[len("avformat:"):] for a in sys.argv if a.startswith("avformat:"))
    with open(wav, "wb") as f:
        f.write(b"RIFF\\x00" * 4)
"""
    p = path / f"melt_{kind}.py"
    p.write_text(script)
    p.chmod(0o755)
    return p


def _fake_ffmpeg(path: Path, out_name: str) -> Path:
    # fake ffmpeg: consumes stdin fully, writes output file; kind=fail
    # exits 2 after writing stderr.
    script = """#!/usr/bin/env python3
import sys
data = sys.stdin.buffer.read()
out = [a for a in sys.argv if a.endswith(".mp4")][0]
open(out, "wb").write(data[:100] if data else b"")
sys.stderr.write("fake ffmpeg ok\\n")
"""
    p = path / "ffmpeg.py"
    p.write_text(script)
    p.chmod(0o755)
    return p


def _cmds(tmp_path: Path, *, melt_kind: str = "video", audio_kind: str = "audio") -> PipeCommands:
    melt = _fake_melt(tmp_path, melt_kind)
    melt_audio = _fake_melt(tmp_path, audio_kind)
    ffmpeg = _fake_ffmpeg(tmp_path, "out.mp4")
    out = tmp_path / "out.mp4"
    audio_wav = tmp_path / "audio.wav"
    return PipeCommands(
        melt_video_cmd=[str(melt), "video"],
        melt_audio_cmd=[str(melt_audio), "audio", "-consumer", f"avformat:{audio_wav}", "-format", "wav"],
        ffmpeg_cmd=[str(ffmpeg), "-i", "-", "-i", str(audio_wav), str(out)],
        audio_wav=audio_wav,
    )


def test_run_pipe_success(tmp_path: Path):
    cmds = _cmds(tmp_path)
    result = run_pipe(cmds, timeout_s=30)
    assert result.returncode == 0
    assert result.melt_rc == 0 and result.ffmpeg_rc == 0
    assert "fake ffmpeg ok" in result.stderr
    assert cmds.audio_wav.is_file() and cmds.audio_wav.stat().st_size > 0
    assert (tmp_path / "out.mp4").is_file()
    assert (tmp_path / "out.mp4").stat().st_size > 0


def test_run_pipe_audio_pass_failure(tmp_path: Path):
    result = run_pipe(_cmds(tmp_path, audio_kind="fail"), timeout_s=30)
    assert result.returncode != 0
    assert "fake melt exploded" in result.stderr


def test_run_pipe_melt_failure(tmp_path: Path):
    cmds = _cmds(tmp_path)
    cmds = PipeCommands([sys.executable, "-c", "import sys; sys.stderr.write('boom'); sys.exit(3)"],
                        cmds.melt_audio_cmd, cmds.ffmpeg_cmd, cmds.audio_wav)
    result = run_pipe(cmds, timeout_s=30)
    assert result.returncode == 3
    assert "boom" in result.stderr


def test_run_pipe_ffmpeg_failure(tmp_path: Path):
    cmds = _cmds(tmp_path)
    bad_ff = tmp_path / "ff_fail.py"
    bad_ff.write_text("#!/usr/bin/env python3\nimport sys\nsys.stdin.buffer.read()\nsys.stderr.write('ff died')\nsys.exit(2)\n")
    bad_ff.chmod(0o755)
    cmds = PipeCommands(cmds.melt_video_cmd, cmds.melt_audio_cmd,
                        [str(bad_ff), "-i", "-", str(tmp_path / "x.mp4")], cmds.audio_wav)
    result = run_pipe(cmds, timeout_s=30)
    assert result.returncode == 2
    assert "ff died" in result.stderr


def test_run_pipe_timeout(tmp_path: Path):
    cmds = _cmds(tmp_path)
    slow_ff = tmp_path / "ff_slow.py"
    slow_ff.write_text("#!/usr/bin/env python3\nimport time\ntime.sleep(60)\n")
    slow_ff.chmod(0o755)
    cmds = PipeCommands(cmds.melt_video_cmd, cmds.melt_audio_cmd,
                        [str(slow_ff)], cmds.audio_wav)
    with pytest.raises(PipeRunError, match="timed out"):
        run_pipe(cmds, timeout_s=1)


def test_run_pipe_spawn_failure_kills_melt(tmp_path: Path):
    cmds = _cmds(tmp_path)
    cmds = PipeCommands(cmds.melt_video_cmd, cmds.melt_audio_cmd,
                        [str(tmp_path / "no_such_ffmpeg")], cmds.audio_wav)
    with pytest.raises(PipeRunError, match="pipe spawn failed"):
        run_pipe(cmds, timeout_s=30)


def _frame_pipe_cmds(tmp_path: Path) -> tuple[PipeCommands, FrameOverlaySpec]:
    video = tmp_path / "tiny_melt_video.py"
    video.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "sys.stdout.buffer.write(b'base')\n"
    )
    video.chmod(0o755)
    audio = tmp_path / "tiny_melt_audio.py"
    audio.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "path = next(a[len('avformat:'):] for a in sys.argv if a.startswith('avformat:'))\n"
        "open(path, 'wb').write(b'RIFF')\n"
    )
    audio.chmod(0o755)
    ffmpeg = tmp_path / "tiny_ffmpeg.py"
    ffmpeg.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        "overlay = os.read(3, 1024 * 1024)\n"
        "sys.stdin.buffer.read()\n"
        "out = next(a for a in sys.argv if a.endswith('.mp4'))\n"
        "open(out, 'wb').write(overlay)\n"
    )
    ffmpeg.chmod(0o755)
    overlay = FrameOverlaySpec(
        composition_uid="uid-1",
        composition_id="TitleCard",
        entry_point="src/index.ts",
        props={"titleText": "Hi"},
        position_sec=0.0,
        duration_sec=1.0,
        width=64,
        height=64,
        fps=30.0,
        alpha=False,
        pipe_fd=3,
    )
    return (
        PipeCommands(
            [str(video)],
            [str(audio), "-consumer", f"avformat:{tmp_path / 'audio.wav'}"],
            [str(ffmpeg), str(tmp_path / "out.mp4")],
            tmp_path / "audio.wav",
            frame_overlays=[overlay],
            frame_pipe_fds=(3,),
        ),
        overlay,
    )


def test_run_pipe_feeds_frames_after_ffmpeg_starts_and_closes_client(
    tmp_path: Path,
):
    cmds, _overlay = _frame_pipe_cmds(tmp_path)
    requests = []

    class FakeClient:
        closed = False

        def request_frame(self, request):
            requests.append(request)
            return SimpleNamespace(bytes=b"\x89PNG" + bytes([request.frame % 256]))

        def close(self):
            self.closed = True

    client = FakeClient()
    result = run_pipe(cmds, timeout_s=30, frame_clients=[client])

    assert result.returncode == 0
    assert result.frames_requested == 30
    assert [request.frame for request in requests] == list(range(30))
    assert client.closed is True
    assert (tmp_path / "out.mp4").read_bytes().startswith(b"\x89PNG")


def test_run_pipe_surfaces_frame_server_failure_and_closes_client(tmp_path: Path):
    cmds, _overlay = _frame_pipe_cmds(tmp_path)

    class ErrorClient:
        closed = False

        def request_frame(self, _request):
            raise RuntimeError("frame server exploded")

        def close(self):
            self.closed = True

    client = ErrorClient()
    with pytest.raises(PipeRunError, match="frame feeder failed"):
        run_pipe(cmds, timeout_s=30, frame_clients=[client])
    assert client.closed is True


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is required")
def test_run_pipe_frame_overlay_reaches_real_ffmpeg(tmp_path: Path):
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg is not None
    profile = select_profile("fast_proxy").model_copy(
        update={"width": 64, "height": 64},
    )
    overlay_png = tmp_path / "overlay.png"
    subprocess.run(
        [
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=red@0.5:s=64x64:d=0.1",
            "-frames:v", "1", "-vf", "format=rgba", str(overlay_png),
        ],
        check=True,
        timeout=30,
    )
    overlay = FrameOverlaySpec(
        composition_uid="uid-real",
        composition_id="TitleCard",
        entry_point="src/index.ts",
        props={},
        position_sec=0.0,
        duration_sec=0.1,
        width=64,
        height=64,
        fps=30.0,
        alpha=True,
    )
    built = build_pipe_commands(
        "melt",
        tmp_path / "timeline.mlt",
        tmp_path / "real.mp4",
        profile,
        select_encoder("cpu", final=False),
        [overlay],
        frame_engine="pull",
        workdir=tmp_path,
    )
    video = tmp_path / "tiny_video.py"
    video.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "frame = b'\\x80' * (64 * 64 * 3 // 2)\n"
        "sys.stdout.buffer.write(frame * 3)\n"
    )
    video.chmod(0o755)
    audio = tmp_path / "tiny_audio.py"
    audio.write_text(
        "#!/usr/bin/env python3\n"
        "import sys, wave\n"
        "path = next(a[len('avformat:'):] for a in sys.argv if a.startswith('avformat:'))\n"
        "with wave.open(path, 'wb') as f:\n"
        "    f.setnchannels(1); f.setsampwidth(2); f.setframerate(48000)\n"
        "    f.writeframes(b'\\0\\0' * 4800)\n"
    )
    audio.chmod(0o755)
    cmds = PipeCommands(
        [str(video)],
        [str(audio), "-consumer", f"avformat:{built.audio_wav}"],
        built.ffmpeg_cmd,
        built.audio_wav,
        frame_overlays=built.frame_overlays,
        frame_pipe_fds=built.frame_pipe_fds,
    )

    class FakeClient:
        def request_frame(self, _request):
            return SimpleNamespace(bytes=overlay_png.read_bytes())

    result = run_pipe(cmds, timeout_s=30, frame_clients=[FakeClient()])

    assert result.returncode == 0, result.stderr
    assert result.frames_requested == 3
    assert (tmp_path / "real.mp4").is_file()
