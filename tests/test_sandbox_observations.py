"""Verify the strace observation fixtures are present and parseable."""
from pathlib import Path

OBS_DIR = Path(__file__).parent.parent / "sandbox" / "observations"


def test_strace_melt_fixture_exists() -> None:
    path = OBS_DIR / "strace_melt.txt"
    assert path.exists(), f"missing {path}"
    content = path.read_text()
    assert "seconds" in content or "syscall" in content.lower()


def test_strace_ffmpeg_fixture_exists() -> None:
    path = OBS_DIR / "strace_ffmpeg.txt"
    assert path.exists(), f"missing {path}"
    assert path.stat().st_size > 0


def test_strace_ffprobe_fixture_exists() -> None:
    path = OBS_DIR / "strace_ffprobe.txt"
    assert path.exists(), f"missing {path}"
    assert path.stat().st_size > 0


def test_strace_files_contain_real_syscalls() -> None:
    """Each strace file should list at least 5 distinct syscalls."""
    for name in ("strace_melt.txt", "strace_ffmpeg.txt", "strace_ffprobe.txt"):
        content = (OBS_DIR / name).read_text()
        syscall_lines = [
            line for line in content.splitlines()
            if line and line.split() and not line.startswith("-")
            and not line.startswith("%")
            and not line.startswith("syscall")
        ]
        assert len(syscall_lines) >= 5, f"{name} has too few syscalls: {syscall_lines}"
