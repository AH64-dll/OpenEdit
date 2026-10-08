"""Configurable local exports from a fixed source revision, published atomically."""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import uuid
from fractions import Fraction
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator

from open_edit.ir.derive import derive_timeline
from open_edit.ir.types import Project, Timeline
from open_edit.storage.assets import AssetStore, list_assets_from_disk
from open_edit.storage.edit_graph import EditGraphStore, GraphRevisionConflict


class ExportSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str = Field(default="OpenEdit export", min_length=1, max_length=128)
    folder: str | None = Field(default=None, max_length=4096)
    width: StrictInt = Field(default=1920, ge=16, le=7680)
    height: StrictInt = Field(default=1080, ge=16, le=7680)
    fps_num: StrictInt = Field(default=30, ge=1, le=240000)
    fps_den: StrictInt = Field(default=1, ge=1, le=10000)
    container: Literal["mp4", "mov", "mkv", "webm"] = "mp4"
    codec: Literal["h264", "hevc", "av1"] = "h264"
    encoder: Literal["auto", "cpu", "gpu"] = "auto"
    quality: Literal["fast", "standard", "high", "archival"] = "standard"
    rate_control: Literal["quality", "crf", "bitrate"] = "quality"
    crf: StrictInt = Field(default=18, ge=0, le=51)
    bitrate_mbps: float = Field(default=10, ge=0.1, le=500, allow_inf_nan=False)
    speed: Literal["fast", "balanced", "slow"] = "balanced"
    range_mode: Literal["full", "range"] = "full"
    start_sec: float = Field(default=0, ge=0, allow_inf_nan=False)
    end_sec: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    audio: StrictBool = True
    audio_codec: Literal["aac", "opus", "pcm_s16le"] = "aac"
    audio_bitrate_kbps: StrictInt = Field(default=320, ge=32, le=512)
    audio_sample_rate: Literal[44100, 48000, 96000] = 48000
    audio_channels: Literal[1, 2] = 2
    captions: Literal["burn", "none"] = "burn"
    color_space: Literal["SDR Rec.709"] = "SDR Rec.709"

    @model_validator(mode="after")
    def supported_combination(self):
        if self.width % 2 or self.height % 2:
            raise ValueError("Export dimensions must be even")
        if not 1 <= self.fps_num / self.fps_den <= 120:
            raise ValueError("Export frame rate must be between 1 and 120")
        if self.range_mode == "range" and (self.end_sec is None or self.end_sec <= self.start_sec):
            raise ValueError("Choose a range with its end after its start")
        if self.range_mode == "range" and round(
            self.end_sec * self.fps_num / self.fps_den
        ) <= round(self.start_sec * self.fps_num / self.fps_den):
            raise ValueError("Export range must contain at least one frame")
        if self.folder and not Path(self.folder).expanduser().is_absolute():
            raise ValueError("Export folder must be an absolute local path")
        if self.audio and self.audio_codec == "opus" and self.audio_sample_rate != 48000:
            raise ValueError("Opus exports use a 48000 Hz sample rate")
        if self.container == "webm" and (
            self.codec != "av1" or (self.audio and self.audio_codec != "opus")
        ):
            raise ValueError("WebM requires AV1 video and Opus audio")
        if self.container == "mov" and self.codec == "av1":
            raise ValueError("Choose MP4, MKV or WebM for AV1")
        if self.audio and self.container in ("mp4", "mov") and self.audio_codec != "aac":
            raise ValueError("MP4 and MOV exports use AAC audio")
        if (
            re.search(r'[<>:"/\\|?*\x00-\x1f]', self.filename)
            or self.filename.endswith((".", " "))
            or self.filename in (".", "..")
        ):
            raise ValueError("Filename must be a plain portable filename")
        stem = self.filename.rsplit(".", 1)[0].upper()
        if stem in {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10)),
        }:
            raise ValueError("Choose a filename that works on Windows too")
        return self


def desktop_directory() -> Path:
    """Respect redirected Windows desktops and XDG desktop localization."""
    if os.name == "nt":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
            ) as key:
                return Path(os.path.expandvars(winreg.QueryValueEx(key, "Desktop")[0]))
        except OSError:
            pass
    xdg = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "user-dirs.dirs"
    if xdg.is_file():
        match = re.search(r'^XDG_DESKTOP_DIR="([^"]+)"', xdg.read_text(), re.M)
        if match:
            return Path(match[1].replace("$HOME", str(Path.home()))).expanduser()
    return Path.home() / "Desktop"


def project_timeline(root: Path) -> Timeline:
    store = EditGraphStore(root / ".open_edit/edit_graph.db")
    return derive_timeline(
        Project(
            name=root.name,
            workdir=root,
            edit_graph=store.load_all(),
            assets={a.asset_hash: a for a in list_assets_from_disk(root)},
        ),
        strict=True,
    )


def export_defaults(root: Path) -> dict:
    timeline = project_timeline(root)
    assets = {a.asset_hash: a for a in list_assets_from_disk(root)}
    media = next(
        (
            assets[c.asset_hash]
            for t in timeline.tracks
            if t.kind == "video"
            for c in sorted(t.clips, key=lambda c: c.position_sec)
            if c.asset_hash in assets
        ),
        None,
    )
    doc = next(iter(timeline.graphics_documents.values()), None)
    scene = {}
    if doc and not media:
        from open_edit.integrations.diffusion.graphics import inspect_source

        scene = inspect_source(doc["source"])["scene"]
    width = (media.width if media else scene.get("width")) or 1920
    height = (media.height if media else scene.get("height")) or 1080
    fps = Fraction(
        str((media.fps if media else doc.get("fps") if doc else None) or 30)
    ).limit_denominator(1001)
    settings = ExportSettings(
        filename=re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", root.name).strip(" .") or "OpenEdit export",
        width=max(16, min(7680, width // 2 * 2)),
        height=max(16, min(7680, height // 2 * 2)),
        fps_num=fps.numerator,
        fps_den=fps.denominator,
        folder=str(desktop_directory()),
    )
    return {
        "settings": settings.model_dump(mode="json"),
        "duration_sec": timeline.duration_sec,
        "graph_revision": EditGraphStore(root / ".open_edit/edit_graph.db").graph_revision(),
        "presets": [
            {
                "name": "Project",
                "width": settings.width,
                "height": settings.height,
                "fps_num": settings.fps_num,
                "fps_den": settings.fps_den,
            },
            {"name": "1080p", "width": 1920, "height": 1080, "fps_num": 30, "fps_den": 1},
            {"name": "720p", "width": 1280, "height": 720, "fps_num": 30, "fps_den": 1},
            {"name": "Vertical", "width": 1080, "height": 1920, "fps_num": 30, "fps_den": 1},
            {"name": "Square", "width": 1080, "height": 1080, "fps_num": 30, "fps_den": 1},
        ],
    }


def capture_export(root: Path, expected_revision: int, settings: ExportSettings) -> dict:
    """Freeze the database and referenced bytes before any background rendering."""
    nonce = uuid.uuid4().hex
    folder = root / ".open_edit/exports" / nonce
    frozen = folder / "project"
    frozen_data = frozen / ".open_edit"
    frozen_data.mkdir(parents=True)
    try:
        with (
            sqlite3.connect(root / ".open_edit/edit_graph.db") as src,
            sqlite3.connect(frozen_data / "edit_graph.db") as dst,
        ):
            src.backup(dst)
        store = EditGraphStore(frozen_data / "edit_graph.db")
        revision = store.graph_revision()
        if revision != expected_revision:
            raise GraphRevisionConflict(expected_revision, revision)
        # CAS bytes are immutable; hard links retain them even if the original
        # project later drops an asset. Sidecars are mutable and must be copied.
        original = AssetStore(root / ".open_edit/assets")
        target = AssetStore(frozen_data / "assets")
        for asset in list_assets_from_disk(root):
            source = original.path(asset.asset_hash)
            if source is None:
                raise ValueError(f"Missing source media: {asset.asset_hash}")
            dest = target._cas_path(asset.asset_hash)
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(source, dest)
            except OSError:
                shutil.copy2(source, dest)
            cloned = asset.model_copy(
                update={"stored_path": str(dest), "proxy_hash": None, "proxy_status": "none"}
            )
            target._sidecar_path(asset.asset_hash).write_text(
                cloned.model_dump_json(), encoding="utf-8"
            )
        for name in ("remotion", "fonts"):
            source = root / ".open_edit" / name
            if source.is_dir():
                shutil.copytree(
                    source,
                    frozen_data / name,
                    ignore=shutil.ignore_patterns("node_modules", ".cache", "out", "tmp"),
                )
        timeline = project_timeline(frozen)
        if timeline.duration_sec <= 0:
            raise ValueError("Add media or a composition before exporting")
        if settings.range_mode == "range" and settings.end_sec > timeline.duration_sec + 1e-6:
            raise ValueError("Export range extends beyond the project")
        # Capture legacy HTML templates and adjacent styles/images as source.
        for overlay in timeline.overlays:
            from open_edit.render.html_overlay import _resolve_template_path

            source = _resolve_template_path(overlay.template_path, root)
            if not source.is_relative_to(root.resolve()):
                continue  # Package-owned builtin template, already pinned with this app.
            relative = source.relative_to(root.resolve())
            if source.parent == root.resolve():
                for sibling in root.iterdir():
                    if sibling.is_file() and sibling.suffix.lower() in (
                        ".html",
                        ".css",
                        ".js",
                        ".json",
                        ".svg",
                        ".png",
                        ".jpg",
                        ".jpeg",
                        ".webp",
                        ".woff",
                        ".woff2",
                        ".ttf",
                    ):
                        shutil.copy2(sibling, frozen / sibling.name)
                continue
            if ".open_edit/exports" in str(relative):
                raise ValueError("HTML templates must be source files outside export snapshots")
            dest = frozen / relative.parent
            shutil.copytree(
                source.parent,
                dest,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("node_modules", ".cache", "out", "tmp"),
            )
        payload = {
            "snapshot": nonce,
            "settings": settings.model_dump(mode="json"),
            "graph_revision": revision,
        }
        (folder / "export.json").write_text(json.dumps(payload, allow_nan=False), encoding="utf-8")
        return payload
    except BaseException:
        shutil.rmtree(folder)
        raise


def verify_export(
    path: Path, settings: ExportSettings, duration: float, *, expected_audio: bool | None = None
) -> dict:
    from open_edit.storage.assets import _probe_media

    info = _probe_media(str(path))
    if (info.get("width"), info.get("height")) != (settings.width, settings.height):
        raise ValueError("Export has incorrect dimensions")
    fps = settings.fps_num / settings.fps_den
    if abs(info.get("fps", 0) - fps) > 0.02 or abs(info.get("duration_sec", 0) - duration) > max(
        0.15, 2 / fps
    ):
        raise ValueError("Export has incorrect frame rate or duration")
    expected_codec = {"h264": "h264", "hevc": "hevc", "av1": "av1"}[settings.codec]
    if info.get("codec") != expected_codec:
        raise ValueError("Export has an unexpected video codec")
    # Complete decoding catches truncated packets which a metadata probe misses.
    result = subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-xerror",
            "-i",
            str(path),
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        timeout=max(120, min(14400, duration * 10)),
    )
    if result.returncode:
        raise ValueError(
            "Export failed its complete decode check: "
            + result.stderr.decode(errors="replace")[-1000:]
        )
    if not settings.audio and info.get("has_audio"):
        raise ValueError("Export unexpectedly contains audio")
    if expected_audio is not None and bool(info.get("has_audio")) != expected_audio:
        raise ValueError("Export lost its expected audio stream")
    if info.get("has_audio"):
        stream = json.loads(
            subprocess.check_output(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "a:0",
                    "-show_streams",
                    "-of",
                    "json",
                    str(path),
                ]
            )
        )["streams"][0]
        if (
            stream["codec_name"] != settings.audio_codec
            or int(stream["sample_rate"]) != settings.audio_sample_rate
            or stream["channels"] != settings.audio_channels
        ):
            raise ValueError("Export has incorrect audio settings")
    return {
        "passed": True,
        "complete": True,
        "dimensions": [settings.width, settings.height],
        "fps": fps,
        "duration_sec": info["duration_sec"],
        "codec": info["codec"],
        "audio": info.get("has_audio", False),
        "full_decode": True,
    }


def publish_export(source: Path, settings: ExportSettings, duration: float) -> tuple[Path, dict]:
    """Verify on the destination filesystem, then atomically create a unique name."""
    folder = Path(settings.folder).expanduser() if settings.folder else desktop_directory()
    if not folder.is_absolute():
        raise ValueError("Export folder must be an absolute local path")
    folder.mkdir(parents=True, exist_ok=True)
    stem = settings.filename
    if stem.lower().endswith("." + settings.container):
        stem = stem[: -(len(settings.container) + 1)]
    if not stem:
        raise ValueError("Choose an export filename")
    handle, pending = tempfile.mkstemp(
        prefix=".openedit-export-", suffix="." + settings.container, dir=folder
    )
    os.close(handle)
    temporary = Path(pending)
    try:
        args = [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-c:v",
            "copy",
        ]
        if settings.audio:
            args += [
                "-map",
                "0:a?",
                "-c:a",
                settings.audio_codec,
                "-ar",
                str(settings.audio_sample_rate),
                "-ac",
                str(settings.audio_channels),
            ]
            if settings.audio_codec != "pcm_s16le":
                args += ["-b:a", f"{settings.audio_bitrate_kbps}k"]
        else:
            args += ["-an"]
        if settings.container in ("mp4", "mov"):
            args += ["-movflags", "+faststart"]
        if settings.codec == "hevc" and settings.container in ("mp4", "mov"):
            args += ["-tag:v", "hvc1"]
        args += [
            "-color_primaries",
            "bt709",
            "-color_trc",
            "bt709",
            "-colorspace",
            "bt709",
            str(temporary),
        ]
        result = subprocess.run(
            args, capture_output=True, timeout=max(120, min(14400, duration * 10))
        )
        if result.returncode:
            raise ValueError(
                "Export packaging failed: " + result.stderr.decode(errors="replace")[-1000:]
            )
        from open_edit.storage.assets import _probe_media

        report = verify_export(
            temporary,
            settings,
            duration,
            expected_audio=settings.audio and bool(_probe_media(str(source)).get("has_audio")),
        )
        with temporary.open("rb") as file:
            os.fsync(file.fileno())
        for index in range(10000):
            final = folder / f"{stem}{f' ({index + 1})' if index else ''}.{settings.container}"
            try:
                os.link(temporary, final)
                return final, report
            except FileExistsError:
                continue
        raise ValueError("Too many exports share this filename; choose another name")
    finally:
        temporary.unlink(missing_ok=True)


def execute_export(root: Path, payload: dict) -> dict:
    """Worker entry point. Later project edits cannot change this render."""
    from open_edit.render.encoder import resolve_backend, select_encoder
    from open_edit.render.orchestrator import render_project
    from open_edit.render.preview_invalidation import slice_timeline

    nonce = payload["snapshot"]
    if not re.fullmatch(r"[a-f0-9]{32}", nonce):
        raise ValueError("Invalid export snapshot")
    folder = root / ".open_edit/exports" / nonce
    captured = json.loads((folder / "export.json").read_text())
    if captured != payload:
        raise ValueError("Export snapshot settings changed")
    settings = ExportSettings.model_validate(captured["settings"])
    frozen = folder / "project"
    timeline = project_timeline(frozen)
    if settings.range_mode == "range":
        fps = settings.fps_num / settings.fps_den
        timeline = slice_timeline(
            timeline,
            render_start_frame=round(settings.start_sec * fps),
            render_end_frame=round(settings.end_sec * fps),
            fps_num=settings.fps_num,
            fps_den=settings.fps_den,
            plane="both",
        )
    backend = None if settings.encoder == "auto" else settings.encoder
    encoder = select_encoder(backend, tier=settings.quality, codec=settings.codec)
    speed = settings.speed
    if encoder.vcodec.endswith("_nvenc"):
        preset = {"fast": "p2", "balanced": "p5", "slow": "p7"}[speed]
    elif encoder.vcodec == "libsvtav1":
        preset = {"fast": "10", "balanced": "8", "slow": "4"}[speed]
    elif encoder.vcodec in ("libx264", "libx265") or encoder.vcodec.endswith("_qsv"):
        preset = {"fast": "veryfast", "balanced": "medium", "slow": "slow"}[speed]
    else:
        preset = None
    overrides = {
        "width": settings.width,
        "height": settings.height,
        "frame_rate_num": settings.fps_num,
        "frame_rate_den": settings.fps_den,
        "codec": settings.codec,
        "preset": preset,
    }
    if settings.rate_control == "crf":
        overrides["crf"] = settings.crf
    if settings.rate_control == "bitrate":
        overrides["vb"] = f"{round(settings.bitrate_mbps * 1000)}k"
    result = render_project(
        project_id=root.name,
        project_dir=frozen,
        workdir=folder / "render",
        mode="final",
        quality=settings.quality,
        overrides=overrides,
        encoder_backend=backend,
        timeline_override=timeline,
        force=True,
    )
    if not result.ok:
        raise ValueError(result.error or "Export render failed")
    final, report = publish_export(Path(result.output_path), settings, timeline.duration_sec)
    out = result.model_dump(mode="json")
    out.update(
        output_path=str(final),
        export_settings=settings.model_dump(mode="json"),
        export_verification=report,
        export_snapshot=nonce,
        graph_revision=captured["graph_revision"],
        encoder_backend=resolve_backend(backend),
        duration_sec=timeline.duration_sec,
    )
    out["encoder"] = encoder.vcodec
    return out
