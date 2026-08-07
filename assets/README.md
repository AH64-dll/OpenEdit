# Media Assets Directory Structure & Guidelines (`assets/`)

This directory contains the central media asset library for the `mlt-pipeline` / `OpenEdit` AI video editing system. 

It is organized into standardized, machine-readable categories following industry standards: the **Universal Category System (UCS)** for audio and professional post-production taxonomies for visual effects.

---

## 1. Directory Structure

```
assets/
├── audio/
│   ├── sfx/                # Sound effects (UCS: Impact, Whoosh, Riser, UI, Glitch, Foley, Cinematic)
│   ├── ambience/           # Environmental background audio (Room tone, City, Nature, Space)
│   └── music/              # Background tracks, stingers, stems
└── video/
    ├── overlays/           # Film grain, light leaks, dust particles, CRT/VHS textures
    ├── transitions/        # Wipes, zooms, glitches, whip pans, film burns
    ├── motion_graphics/    # Lower thirds, callouts, titles, progress bars, subscriber badges
    ├── elements/           # Alpha channel VFX (Smoke, Fire, Sparks, Explosions, HUD graphics)
    └── backgrounds/        # Looping motion backgrounds, gradients, particle streams
```

---

## 2. Naming Standards (English Only)

Every asset file **must** follow the strict naming convention so that language models and automated indexers can determine file type, category, descriptor, and variant without opening the media.

### Naming Formula:
`[type]_[category]_[descriptor]_[variant].[extension]`

- **`type`**: `sfx`, `ambience`, `music`, `vfx`, `gfx`, `bg`, `transition`
- **`category`**: `impact`, `whoosh`, `riser`, `ui`, `glitch`, `overlay`, `element`, `lower_third`, etc.
- **`descriptor`**: Specific English description of the sound or visual effect (e.g. `heavy_explosion`, `fast_air`, `light_leak_warm`, `film_grain_35mm`).
- **`variant`**: Variant number (e.g. `01`, `02`) or resolution (`4k`, `1080p`).

### Examples:
- `assets/audio/sfx/sfx_impact_heavy_explosion_01.wav`
- `assets/audio/sfx/sfx_whoosh_fast_air_02.wav`
- `assets/audio/sfx/sfx_ui_click_soft_01.wav`
- `assets/video/overlays/vfx_overlay_light_leak_warm_4k.mov`
- `assets/video/overlays/vfx_overlay_film_grain_35mm.mov`
- `assets/video/transitions/vfx_transition_glitch_digital_01.mp4`
- `assets/video/elements/vfx_element_fire_large_alpha.mov`
- `assets/video/motion_graphics/gfx_lower_third_modern_blue.json`

---

## 3. Rules & Contribution Guidelines

1. **Lowercase Only**: Use lowercase ASCII letters, numbers, and underscores. No spaces, dashes, or special characters.
2. **Audio Specs**: Preferred format `.wav` (48kHz / 24-bit or 16-bit uncompressed) or high-quality `.mp3`.
3. **Video Specs**: Preferred formats `.mov` (ProRes 4444 with Alpha / ProRes 422) or `.mp4` (H.264 / HEVC).
4. **Transparency (Alpha Channel)**: VFX elements (smoke, explosions, callouts) must retain alpha channels or use pure black backgrounds intended for `Screen`/`Add` blend modes.
5. **Automatic Indexing**: After adding or modifying assets in this folder, re-run the asset indexer to update the AI registry:
   ```bash
   python3 -m open_edit.asset_indexer
   ```
