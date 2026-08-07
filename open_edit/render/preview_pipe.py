"""Independent preview video/audio plane and cheap mux command builders."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from open_edit.render.encoder import EncoderSpec
from open_edit.render.pipe_builder import OverlayClip, overlay_filter_chain
from open_edit.render.profiles import RenderProfile

PreviewMedia = Literal["video", "audio", "both"]


@dataclass(frozen=True)
class PreviewPipeCommands:
    """Commands needed to produce the selected preview plane artifacts."""

    video_cmd: list[str] | None
    audio_cmd: list[str] | None
    mux_cmd: list[str] | None
    video_output: Path | None
    audio_output: Path | None
    playback_output: Path


def _fps_string(profile: RenderProfile) -> str:
    if profile.frame_rate_den == 1:
        return str(profile.frame_rate_num)
    return f"{profile.frame_rate_num}/{profile.frame_rate_den}"


def _size_string(profile: RenderProfile) -> str:
    if profile.scale:
        return profile.scale
    return f"{profile.width}x{profile.height}"


def _seconds(frame: int, profile: RenderProfile) -> str:
    value = frame * profile.frame_rate_den / profile.frame_rate_num
    return f"{value:.9f}".rstrip("0").rstrip(".") or "0"


def _validate_range(
    crop_head_frames: int,
    crop_tail_frames: int,
    core_frames: int,
) -> tuple[int, int]:
    values = (
        ("crop_head_frames", crop_head_frames),
        ("crop_tail_frames", crop_tail_frames),
        ("core_frames", core_frames),
    )
    for name, value in values:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{name} must be a non-negative integer")
    if core_frames == 0:
        raise ValueError("core_frames must be positive")
    render_frames = crop_head_frames + core_frames + crop_tail_frames
    return render_frames - crop_tail_frames, render_frames


def _validate_preview_geometry(profile: RenderProfile) -> None:
    if profile.name != "preview_chunk":
        return
    if (profile.width, profile.height) != (640, 360) or profile.scale:
        raise ValueError("preview_chunk geometry is fixed at 640x360")


def _pipeline(producer: list[str], consumer: list[str]) -> list[str]:
    """Represent the host-side producer/consumer pipe as one command spec."""
    return [*producer, "|", *consumer]


def _build_video_command(
    *,
    melt_bin: str,
    xml_path: Path,
    output: Path,
    profile: RenderProfile,
    encoder: EncoderSpec,
    overlays: Sequence[OverlayClip],
    crop_head_frames: int,
    core_frames: int,
    render_end_frame: int,
) -> list[str]:
    size = _size_string(profile)
    fps = _fps_string(profile)
    melt_cmd = [
        melt_bin, str(xml_path),
        "-consumer", "avformat:pipe:",
        # Keep this spelling: ffmpeg consumes the actual rawvideo muxer stream.
        "f=rawvideo",
        "vcodec=rawvideo",
        "pix_fmt=nv12",
        f"s={size}",
        f"frame_rate_num={profile.frame_rate_num}",
        f"frame_rate_den={profile.frame_rate_den}",
        "progressive=1",
        "colorspace=709",
    ]
    video_input = [
        "-f", "rawvideo",
        "-pix_fmt", "nv12",
        "-s", size,
        "-r", fps,
        "-i", "-",
    ]
    trim = (
        f"trim=start_frame={crop_head_frames}:"
        f"end_frame={render_end_frame},"
        "setpts=PTS-STARTPTS"
    )
    overlay_list = list(overlays)
    overlay_inputs: list[str] = []
    for overlay in overlay_list:
        overlay_inputs.extend(["-i", str(overlay.media_path)])

    ffmpeg_cmd = ["ffmpeg", "-y", *video_input, *overlay_inputs]
    if overlay_list:
        filters = overlay_filter_chain(
            overlay_list,
            profile.width,
            profile.height,
            first_overlay_input=1,
        )
        filters.append(f"[vout]{trim}[vcore]")
        ffmpeg_cmd += [
            "-filter_complex", ";".join(filters),
            "-map", "[vcore]",
        ]
    else:
        ffmpeg_cmd += ["-vf", trim, "-map", "0:v:0"]
    ffmpeg_cmd += [
        "-an",
        "-c:v", encoder.vcodec,
        *encoder.ffmpeg_args,
        "-frames:v", str(core_frames),
        str(output),
    ]
    return _pipeline(melt_cmd, ffmpeg_cmd)


def _build_audio_command(
    *,
    melt_bin: str,
    xml_path: Path,
    output: Path,
    profile: RenderProfile,
    crop_head_frames: int,
    core_frames: int,
) -> list[str]:
    melt_cmd = [
        melt_bin, str(xml_path),
        "-consumer", "avformat:pipe:",
        "video_off=1",
        "format=wav",
    ]
    start = _seconds(crop_head_frames, profile)
    end = _seconds(crop_head_frames + core_frames, profile)
    duration = _seconds(core_frames, profile)
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-i", "-",
        "-af", f"atrim=start={start}:end={end},asetpts=PTS-STARTPTS",
        "-vn",
        "-c:a", profile.acodec,
        "-b:a", profile.ab or "96k",
        "-t", duration,
        str(output),
    ]
    return _pipeline(melt_cmd, ffmpeg_cmd)


def _mux_temp_path(playback_output: Path) -> Path:
    return playback_output.with_name(
        f".{playback_output.stem}.tmp{playback_output.suffix}"
    )


def _build_mux_command(
    video_output: Path,
    audio_output: Path,
    playback_output: Path,
) -> list[str]:
    return [
        "ffmpeg", "-y",
        "-i", str(video_output),
        "-i", str(audio_output),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "copy",
        "-shortest",
        "-f", "mp4",
        str(_mux_temp_path(playback_output)),
    ]


def build_preview_pipe_commands(
    *,
    melt_bin: str,
    xml_path: Path,
    video_output: Path | None,
    audio_output: Path | None,
    playback_output: Path,
    profile: RenderProfile,
    encoder: EncoderSpec,
    overlays: Sequence[OverlayClip],
    crop_head_frames: int,
    crop_tail_frames: int,
    core_frames: int,
    media: PreviewMedia,
) -> PreviewPipeCommands:
    """Build independent preview plane commands for a sliced local timeline."""
    if media not in ("video", "audio", "both"):
        raise ValueError("media must be video, audio, or both")
    _validate_preview_geometry(profile)
    render_end_frame, _render_frames = _validate_range(
        crop_head_frames, crop_tail_frames, core_frames,
    )

    video_cmd: list[str] | None = None
    audio_cmd: list[str] | None = None
    mux_cmd: list[str] | None = None
    if media in ("video", "both"):
        if video_output is None:
            raise ValueError(f"video_output is required for media={media!r}")
        video_cmd = _build_video_command(
            melt_bin=melt_bin,
            xml_path=xml_path,
            output=video_output,
            profile=profile,
            encoder=encoder,
            overlays=overlays,
            crop_head_frames=crop_head_frames,
            core_frames=core_frames,
            render_end_frame=render_end_frame,
        )
    if media in ("audio", "both"):
        if audio_output is None:
            raise ValueError(f"audio_output is required for media={media!r}")
        audio_cmd = _build_audio_command(
            melt_bin=melt_bin,
            xml_path=xml_path,
            output=audio_output,
            profile=profile,
            crop_head_frames=crop_head_frames,
            core_frames=core_frames,
        )
    if media == "both":
        assert video_output is not None and audio_output is not None
        mux_cmd = _build_mux_command(video_output, audio_output, playback_output)

    return PreviewPipeCommands(
        video_cmd=video_cmd,
        audio_cmd=audio_cmd,
        mux_cmd=mux_cmd,
        video_output=video_output,
        audio_output=audio_output,
        playback_output=playback_output,
    )


__all__ = ["PreviewPipeCommands", "build_preview_pipe_commands"]
