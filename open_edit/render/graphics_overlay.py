"""Burn Remotion (or other) fullscreen graphics onto a base melt MP4 via ffmpeg.

MLT multitrack composite of opaque Remotion clips is unreliable in this
environment; materialize Remotion to CAS, melt the talk timeline without
those graphics clips, then overlay here.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


from open_edit.render.encoder import select_encoder
from open_edit.render.pipe_builder import OverlayClip, overlay_filter_chain


class GraphicsOverlayError(RuntimeError):
    """Raised when ffmpeg cannot burn graphics onto the base render."""


def burn_overlays(
    base_mp4: Path,
    overlays: list[OverlayClip],
    output_mp4: Path,
    *,
    width: int = 1280,
    height: int = 720,
    timeout_s: float = 900.0,
    encoder_backend: str | None = None,
    final: bool = False,
) -> Path:
    """Overlay timed fullscreen clips onto ``base_mp4``; write ``output_mp4``."""
    if not overlays:
        if Path(base_mp4).resolve() != Path(output_mp4).resolve():
            output_mp4.parent.mkdir(parents=True, exist_ok=True)
            output_mp4.write_bytes(Path(base_mp4).read_bytes())
        return output_mp4

    base_mp4 = Path(base_mp4)
    output_mp4 = Path(output_mp4)
    output_mp4.parent.mkdir(parents=True, exist_ok=True)

    for ov in overlays:
        if not ov.media_path.is_file():
            raise GraphicsOverlayError(f"overlay media missing: {ov.media_path}")

    inputs: list[str] = ["-i", str(base_mp4)]
    for ov in overlays:
        inputs += ["-i", str(ov.media_path)]

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

    chain = overlay_filter_chain(overlays, width, height, first_overlay_input=1)
    if blur_windows:
        # Re-point the chain's base video at the blurred [base] output.
        for idx, frag in enumerate(chain):
            if frag.startswith("[0:v]"):
                chain[idx] = frag.replace("[0:v]", "[base]", 1)
                break
    filters += chain

    audio_bitrate = "320k" if final else "192k"
    spec = select_encoder(encoder_backend, final=final)
    cmd = [
        "ffmpeg", "-y", *inputs,
        "-filter_complex", ";".join(filters),
        "-map", "[vout]", "-map", "0:a?",
        "-c:v", spec.vcodec, *spec.ffmpeg_args,
        "-c:a", "aac", "-b:a", audio_bitrate,
        str(output_mp4),
    ]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout_s,
    )
    if proc.returncode != 0 or not output_mp4.is_file() or output_mp4.stat().st_size == 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        raise GraphicsOverlayError(
            detail[-1] if detail else f"ffmpeg overlay exited {proc.returncode}"
        )
    return output_mp4
