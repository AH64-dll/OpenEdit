"""Frame-server pipe: melt -> rawvideo stdout -> ffmpeg single encode.

melt composes the timeline and streams raw frames; ffmpeg applies the
Remotion overlays and performs the single final encode. Audio comes from a
separate cheap melt pass (``video_off=1``) muxed by ffmpeg.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from open_edit.render.encoder import EncoderSpec
from open_edit.render.profiles import RenderProfile


@dataclass(frozen=True)
class OverlayClip:
    position_sec: float
    duration_sec: float
    media_path: Path
    label: str = ""
    # When True, blur the base talk plate under this overlay window so
    # sharp Remotion cards read as the in-focus subject.
    blur_under: bool = False
    # ProRes/Remotion overlays carry alpha; opaque MP4 screen recordings do not.
    alpha: bool = True


@dataclass(frozen=True)
class PipeCommands:
    """The three subprocess commands of one frame-server render."""
    melt_video_cmd: list[str]
    melt_audio_cmd: list[str]
    ffmpeg_cmd: list[str]
    audio_wav: Path


def _fps_string(profile: RenderProfile) -> str:
    if profile.frame_rate_den == 1:
        return str(profile.frame_rate_num)
    return f"{profile.frame_rate_num}/{profile.frame_rate_den}"


def _size(profile: RenderProfile) -> str:
    scale = getattr(profile, "scale", None)
    if scale:
        return scale
    return f"{profile.width}x{profile.height}"


def overlay_filter_chain(
    overlays: list[OverlayClip], width: int, height: int,
    *, first_overlay_input: int = 2,
) -> list[str]:
    """Filter-graph fragments for the overlay burn (pure; formerly the
    ``burn_overlays`` helper). Returns one filter per overlay
    window; the caller joins with ``;`` and maps the last label ``[vout]``."""
    filters: list[str] = []
    blur_windows = [
        (ov.position_sec, ov.position_sec + ov.duration_sec)
        for ov in overlays
        if ov.blur_under
    ]
    if blur_windows:
        # Blur base only during focus windows; sharp elsewhere.
        enable = "+".join(
            f"between(t\\,{start:.3f}\\,{end:.3f})" for start, end in blur_windows
        )
        filters.append(
            f"[0:v]split=2[sharp][toblur];"
            f"[toblur]boxblur=20:10[blurred];"
            f"[sharp][blurred]overlay=0:0:enable='{enable}'[base]"
        )
    last = "[base]" if blur_windows else "[0:v]"
    for i, ov in enumerate(overlays, start=1):
        end = ov.position_sec + ov.duration_sec
        out_label = f"[v{i}]" if i < len(overlays) else "[vout]"
        ov_input = first_overlay_input + i - 1
        if ov.alpha:
            filters.append(
                f"[{ov_input}:v]scale={width}:{height},"
                f"format=rgba,"
                f"setpts=PTS-STARTPTS+{ov.position_sec}/TB[ov{i}]"
            )
        else:
            filters.append(
                f"[{ov_input}:v]scale={width}:{height},"
                f"setpts=PTS-STARTPTS+{ov.position_sec}/TB[ov{i}]"
            )
        filters.append(
            f"{last}[ov{i}]overlay=0:0:format=auto:eof_action=pass:"
            f"enable='between(t,{ov.position_sec:.3f},{end:.3f})'"
            f"{out_label}"
        )
        last = f"[v{i}]"
    return filters


def build_pipe_commands(
    melt_bin: str,
    xml_path: Path,
    output_mp4: Path,
    profile: RenderProfile,
    spec: EncoderSpec,
    overlays: list[OverlayClip],
    *,
    audio_bitrate: str = "192k",
    workdir: Path | None = None,
) -> PipeCommands:
    """Build melt-video, melt-audio, and ffmpeg commands for one render."""
    size = _size(profile)
    fps = _fps_string(profile)
    audio_wav = (workdir or output_mp4.parent) / f"{output_mp4.stem}.audio.wav"

    # IMPORTANT: use ``f=rawvideo`` (muxer), not ``format=rawvideo``.
    # ``format=`` leaves avformat on the default MPEG-PS muxer while still
    # labeling the codec rawvideo; ffmpeg ``-f rawvideo`` then misreads the
    # stream and produces green/corrupt frames (see debug session c7c4ca).
    melt_video_cmd = [
        melt_bin, str(xml_path),
        "-consumer", "avformat:pipe:",
        "f=rawvideo",
        "vcodec=rawvideo",
        "pix_fmt=yuv420p",
        f"s={size}",
        f"frame_rate_num={profile.frame_rate_num}",
        f"frame_rate_den={profile.frame_rate_den}",
        "progressive=1",
        "colorspace=709",
    ]

    melt_audio_cmd = [
        melt_bin, str(xml_path),
        "-consumer", f"avformat:{audio_wav}",
        "video_off=1",
        "format=wav",
    ]

    video_inputs = ["-f", "rawvideo", "-pix_fmt", "yuv420p", "-s", size, "-r", fps, "-i", "-"]
    audio_inputs = ["-i", str(audio_wav)]
    overlay_inputs: list[str] = []
    for ov in overlays:
        overlay_inputs += ["-i", str(ov.media_path)]

    if overlays:
        filters = overlay_filter_chain(overlays, *map(int, size.split("x")))
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            *video_inputs, *audio_inputs, *overlay_inputs,
            "-filter_complex", ";".join(filters),
            "-map", "[vout]", "-map", "1:a?",
            "-c:v", spec.vcodec, *spec.ffmpeg_args,
            "-c:a", profile.acodec, "-b:a", audio_bitrate,
            str(output_mp4),
        ]
    else:
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            *video_inputs, *audio_inputs,
            "-map", "0:v", "-map", "1:a?",
            "-c:v", spec.vcodec, *spec.ffmpeg_args,
            "-c:a", profile.acodec, "-b:a", audio_bitrate,
            str(output_mp4),
        ]

    return PipeCommands(
        melt_video_cmd=melt_video_cmd,
        melt_audio_cmd=melt_audio_cmd,
        ffmpeg_cmd=ffmpeg_cmd,
        audio_wav=audio_wav,
    )
