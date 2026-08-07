"""
Asset Indexer Module for OpenEdit / mlt-pipeline.

Scans the assets directory, extracts technical metadata using ffprobe,
generates semantic tags and AI triggers based on UCS taxonomy and naming conventions,
and outputs open_edit/assets_manifest.json as the single source of truth.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# Semantic Mapping Dictionaries for AI Triggers, Tags, and Blend Modes
TAG_RULES: Dict[str, List[str]] = {
    "explosion": ["action", "combat", "cinematic", "fire", "battle", "danger", "impact"],
    "impact": ["action", "hit", "collision", "heavy", "boom"],
    "whoosh": ["transition", "camera", "fast", "action", "pass_by", "sweep"],
    "riser": ["tension", "suspense", "build_up", "reveal", "transition"],
    "click": ["ui", "button", "interaction", "interface", "soft"],
    "popup": ["ui", "notification", "graphic", "alert", "bright"],
    "keyboard": ["ui", "typing", "tech", "office"],
    "glitch": ["distortion", "tech", "digital", "artifact", "error", "futuristic"],
    "light_leak": ["overlay", "lighting", "warm", "cinematic", "atmosphere", "flare"],
    "film_grain": ["overlay", "texture", "vintage", "retro", "cinematic", "35mm"],
    "dust": ["overlay", "particles", "atmosphere", "soft"],
    "fire": ["vfx", "element", "action", "flame", "hot"],
    "smoke": ["vfx", "element", "atmosphere", "fog", "cloud"],
    "lower_third": ["motion_graphics", "title", "text", "name", "badge"],
    "callout": ["motion_graphics", "annotation", "arrow", "highlight"],
}

TRIGGER_RULES: Dict[str, List[str]] = {
    "explosion": ["dramatic_reveal", "action_collision", "explosion_event"],
    "impact": ["dramatic_moment", "heavy_hit", "scene_emphasis"],
    "whoosh": ["scene_transition", "fast_camera_move", "text_slide_in"],
    "riser": ["suspense_buildup", "pre_reveal", "climax"],
    "click": ["ui_button_click", "tab_switch"],
    "popup": ["ui_modal_appear", "notification"],
    "glitch": ["system_error", "cyberpunk_transition", "digital_corrupt"],
    "light_leak": ["cinematic_transition", "warm_scene_intro"],
    "film_grain": ["vintage_filter", "retro_look"],
    "lower_third": ["speaker_intro", "person_identification"],
    "fire": ["flame_effect", "burn_scene"],
}

BLEND_MODE_RULES: Dict[str, Tuple[str, str]] = {
    "light_leak": ("Screen", "Add"),
    "fire": ("Screen", "Add"),
    "smoke": ("Screen", "Add"),
    "spark": ("Screen", "Add"),
    "hud": ("Screen", "Add"),
    "dust": ("Screen", "Add"),
    "bokeh": ("Screen", "Add"),
    "film_grain": ("Overlay", "Soft Light"),
    "scratches": ("Overlay", "Soft Light"),
    "film_burn": ("Screen", "Overlay"),
}


def run_ffprobe(filepath: str) -> Optional[Dict[str, Any]]:
    """Runs ffprobe on a media file and returns parsed JSON output."""
    if not shutil.which("ffprobe"):
        return None

    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        filepath
    ]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(res.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError):
        return None


def parse_fps(fps_str: str) -> float:
    """Converts a fractional FPS string like '30000/1001' or '30/1' to float."""
    try:
        if "/" in fps_str:
            num, den = fps_str.split("/")
            return round(float(num) / float(den), 2)
        return round(float(fps_str), 2)
    except (ValueError, ZeroDivisionError):
        return 0.0


def extract_file_metadata(filepath: str) -> Dict[str, Any]:
    """Extracts technical audio/video metadata from media files."""
    ext = os.path.splitext(filepath)[1].lower()
    probe_data = run_ffprobe(filepath)

    meta: Dict[str, Any] = {
        "duration_sec": 0.0,
        "media_type": "unknown",
    }

    if ext in [".wav", ".mp3", ".flac", ".aac", ".ogg", ".m4a"]:
        meta["media_type"] = "audio"
        meta["sample_rate"] = 48000
        meta["channels"] = 2
        meta["codec"] = ext.replace(".", "")
    elif ext in [".mp4", ".mov", ".webm", ".mkv", ".avi"]:
        meta["media_type"] = "video"
        meta["width"] = 1920
        meta["height"] = 1080
        meta["fps"] = 30.0
        meta["codec"] = "h264"
        meta["has_alpha"] = False
        meta["pixel_format"] = "yuv420p"
    elif ext in [".json", ".mogrt"]:
        meta["media_type"] = "motion_graphics"
        meta["duration_sec"] = 5.0
        meta["has_alpha"] = True
    elif ext in [".png", ".jpg", ".jpeg", ".svg"]:
        meta["media_type"] = "image"
        meta["width"] = 1920
        meta["height"] = 1080
        meta["has_alpha"] = ext in [".png", ".svg"]

    if probe_data:
        format_info = probe_data.get("format", {})
        if "duration" in format_info:
            try:
                meta["duration_sec"] = round(float(format_info["duration"]), 2)
            except ValueError:
                pass

        streams = probe_data.get("streams", [])
        for stream in streams:
            codec_type = stream.get("codec_type")
            if codec_type == "audio" and meta["media_type"] == "audio":
                meta["sample_rate"] = int(stream.get("sample_rate", 48000))
                meta["channels"] = int(stream.get("channels", 2))
                meta["codec"] = stream.get("codec_name", meta.get("codec"))
            elif codec_type == "video" and meta["media_type"] == "video":
                meta["width"] = int(stream.get("width", 1920))
                meta["height"] = int(stream.get("height", 1080))
                meta["fps"] = parse_fps(stream.get("r_frame_rate", "30/1"))
                meta["codec"] = stream.get("codec_name", meta.get("codec"))
                pix_fmt = stream.get("pix_fmt", "")
                meta["pixel_format"] = pix_fmt
                if any(a in pix_fmt for a in ["alpha", "rgba", "bgra", "yuva"]):
                    meta["has_alpha"] = True

    return meta


def derive_tags_and_triggers(filename: str, rel_path: str) -> Tuple[List[str], List[str], Tuple[str, str]]:
    """Derives semantic tags, AI trigger events, and blend mode recommendations."""
    clean_name = os.path.splitext(filename)[0].lower()
    tokens = re.split(r"[_\-\s]+", clean_name) + [p.lower() for p in rel_path.split(os.sep)]

    tags_set = set()
    triggers_set = set()
    blend_modes = ("Alpha", "Normal")

    for token in tokens:
        for key, tag_list in TAG_RULES.items():
            if key in token:
                tags_set.update(tag_list)

        for key, trigger_list in TRIGGER_RULES.items():
            if key in token:
                triggers_set.update(trigger_list)

        for key, mode_pair in BLEND_MODE_RULES.items():
            if key in token:
                blend_modes = mode_pair

    if not tags_set:
        tags_set.update([t for t in tokens if len(t) > 2])

    if not triggers_set:
        triggers_set.add("general_use")

    return sorted(list(tags_set)), sorted(list(triggers_set)), blend_modes


def index_assets(assets_dir: str) -> List[Dict[str, Any]]:
    """Scans directory and builds structured asset records."""
    assets_dir_path = Path(assets_dir)
    manifest_records: List[Dict[str, Any]] = []

    if not assets_dir_path.exists():
        return manifest_records

    supported_extensions = {
        ".wav", ".mp3", ".flac", ".aac", ".ogg",
        ".mp4", ".mov", ".webm", ".mkv",
        ".json", ".mogrt", ".png", ".jpg"
    }

    for root, _, files in os.walk(assets_dir_path):
        for file in sorted(files):
            ext = os.path.splitext(file)[1].lower()
            if ext not in supported_extensions:
                continue

            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, assets_dir_path.parent)
            filename_no_ext = os.path.splitext(file)[0]

            meta = extract_file_metadata(full_path)
            tags, triggers, (primary_blend, sec_blend) = derive_tags_and_triggers(file, rel_path)

            category = "unknown"
            subcategory = "general"
            parts = Path(rel_path).parts
            if len(parts) >= 3:
                category = parts[1]  # audio / video
                subcategory = parts[2]  # sfx / overlays / transitions / etc.

            record: Dict[str, Any] = {
                "asset_id": filename_no_ext,
                "category": category,
                "subcategory": subcategory,
                "file_path": rel_path,
                "media_type": meta.get("media_type"),
                "duration_sec": meta.get("duration_sec", 0.0),
                "tags": tags,
                "ai_triggers": triggers,
            }

            if meta.get("media_type") == "audio":
                record.update({
                    "sample_rate": meta.get("sample_rate", 48000),
                    "channels": meta.get("channels", 2),
                    "codec": meta.get("codec", "pcm_s16le"),
                    "recommended_lufs": -14 if "sfx" in subcategory else -24,
                    "recommended_volume_db": -8 if "impact" in filename_no_ext else -16,
                    "recommended_fade_in_ms": 10,
                    "recommended_fade_out_ms": 20,
                })
            elif meta.get("media_type") in ["video", "motion_graphics", "image"]:
                record.update({
                    "width": meta.get("width", 1920),
                    "height": meta.get("height", 1080),
                    "fps": meta.get("fps", 30.0),
                    "codec": meta.get("codec", "h264"),
                    "has_alpha": meta.get("has_alpha", False),
                    "recommended_blend_mode": primary_blend,
                    "secondary_blend_mode": sec_blend,
                })

            manifest_records.append(record)

    return manifest_records


def generate_manifest(assets_dir: str = "assets", output_file: str = "open_edit/assets_manifest.json") -> str:
    """Generates the manifest JSON file."""
    records = index_assets(assets_dir)

    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    manifest_data = {
        "version": "1.0.0",
        "total_assets": len(records),
        "assets": records
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2, ensure_ascii=False)

    return output_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan assets directory and generate AI manifest.")
    parser.add_argument("--assets-dir", default="assets", help="Path to assets folder")
    parser.add_argument("--output", default="open_edit/assets_manifest.json", help="Path to output manifest JSON")
    args = parser.parse_args()

    out_path = generate_manifest(args.assets_dir, args.output)
    print(f"✅ Successfully indexed assets into: {out_path}")


if __name__ == "__main__":
    main()
