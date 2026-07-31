"""run_pipe: concurrent melt->ffmpeg execution with fake binaries."""
import sys
from pathlib import Path

import pytest

from open_edit.render.melt_runner import PipeRunError, run_pipe
from open_edit.render.pipe_builder import PipeCommands


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
    with open(sys.argv[sys.argv.index("avformat:") + 1][len("avformat:"):], "wb") as f:
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


def _cmds(tmp_path: Path, *, melt_kind: str = "video") -> PipeCommands:
    melt = _fake_melt(tmp_path, melt_kind)
    ffmpeg = _fake_ffmpeg(tmp_path, "out.mp4")
    out = tmp_path / "out.mp4"
    audio_wav = tmp_path / "audio.wav"
    return PipeCommands(
        melt_video_cmd=[str(melt), "video"],
        melt_audio_cmd=[str(melt), "audio", "-consumer", f"avformat:{audio_wav}", "-format", "wav"],
        ffmpeg_cmd=[str(ffmpeg), "-i", "-", "-i", str(audio_wav), str(out)],
        audio_wav=audio_wav,
    )


def test_run_pipe_success(tmp_path: Path):
    result = run_pipe(_cmds(tmp_path), timeout_s=30)
    assert result.returncode == 0
    assert result.melt_rc == 0 and result.ffmpeg_rc == 0
    assert "fake ffmpeg ok" in result.stderr


def test_run_pipe_audio_pass_failure(tmp_path: Path):
    result = run_pipe(_cmds(tmp_path, melt_kind="fail"), timeout_s=30)
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
