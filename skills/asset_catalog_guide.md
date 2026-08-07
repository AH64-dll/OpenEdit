# AI Asset Catalog & Effect Selection Guide

This guide is the primary knowledge base for AI agents operating within `mlt-pipeline` / `OpenEdit`. It defines how to discover, select, layer, and parameterize audio and visual effects without blind filesystem searching.

---

## 1. Directory Tree & Taxonomy

Media assets are stored under `assets/` and indexed in `open_edit/assets_manifest.json`.

```
assets/
├── audio/
│   ├── sfx/                # Sound effects (UCS: Impact, Whoosh, Riser, UI, Glitch, Foley, Cinematic)
│   ├── ambience/           # Background environments (Room tone, City, Nature, Space)
│   └── music/              # BGM tracks, stingers, stems
└── video/
    ├── overlays/           # Film grain, light leaks, dust particles, CRT/VHS textures
    ├── transitions/        # Wipes, zooms, glitches, whip pans, film burns
    ├── motion_graphics/    # Lower thirds, callouts, titles, progress bars, subscriber graphics
    ├── elements/           # Transparent alpha VFX (Smoke, Fire, Sparks, Explosions, HUD)
    └── backgrounds/        # Looping motion backgrounds, gradients, particles
```

---

## 2. Naming Standards (English Only)

All asset filenames follow the strict formula:
`[type]_[category]_[descriptor]_[variant].[extension]`

### Examples:
- **Audio (SFX)**: `sfx_impact_heavy_explosion_01.wav`, `sfx_whoosh_fast_air_02.wav`, `sfx_ui_click_soft_01.wav`
- **Audio (Ambience)**: `ambience_city_traffic_night_01.wav`
- **VFX Overlays**: `vfx_overlay_light_leak_warm_4k.mov`, `vfx_overlay_film_grain_35mm.mov`
- **VFX Transitions**: `vfx_transition_glitch_digital_01.mp4`, `vfx_transition_whip_pan_left.mp4`
- **VFX Elements (Alpha)**: `vfx_element_fire_large_alpha.mov`, `vfx_element_smoke_plume.mov`
- **Motion Graphics**: `gfx_lower_third_modern_blue.json`

---

## 3. Natural Language AI Trigger Rules

AI agents mapping natural language intent into media elements must use the following semantic triggers:

| User Prompt Intent / Scene Context | Sound Effect Category & Trigger | Visual Asset Category & Trigger | Recommended Blend Mode |
|---|---|---|---|
| **Dramatic explosion / Action collision** | `sfx_impact_heavy_explosion` / `sfx_impact_sub_boom` | `vfx_element_fire` + `vfx_element_explosion` | `Screen` or `Add` |
| **Fast camera move / Scene cut** | `sfx_whoosh_fast_air` / `sfx_whoosh_cinematic` | `vfx_transition_zoom` / `vfx_transition_whip_pan` | Direct cut / Alpha overlay |
| **Building suspense / Reveal moment** | `sfx_riser_tension_3s` / `sfx_riser_reverse` | `vfx_overlay_light_leak` (fadeIn) | `Screen` |
| **Digital error / Tech glitch** | `sfx_glitch_digital` / `sfx_glitch_static` | `vfx_overlay_glitch` / `vfx_transition_glitch` | `Screen` or `Overlay` |
| **UI interaction / Button click / Popup** | `sfx_ui_click_soft` / `sfx_ui_popup_bright` | `gfx_callout` / `gfx_subscribe_badge` | Alpha compositing |
| **Vintage / Nostalgic look** | `ambience_vinyl_crackle` / `sfx_foley_projector` | `vfx_overlay_film_grain_35mm` + `vfx_overlay_film_burn` | `Overlay` or `Soft Light` |
| **Cyberpunk / Tech HUD** | `sfx_ui_keyboard_fast` / `sfx_glitch_digital` | `vfx_element_hud_graphic` + `bg_particle_blue` | `Screen` or `Add` |

---

## 4. Track Layering & Audio Loudness Standards

### 4.1 Audio Track Structure
- **Track A1 (Dialogue / Voiceover)**: Loudness normalized to **-16 LUFS to -18 LUFS**.
- **Track A2 (Sound Effects - SFX)**: Dynamic levels (**-12 LUFS to -18 LUFS** for impacts/whooshes, **-22 LUFS** for subtle UI clicks).
- **Track A3 (Background Music - BGM)**: Normalized to **-24 LUFS**. Auto-ducked by **-6dB to -10dB** when Dialogue (A1) is active.
- **Track A4 (Ambience)**: Low priority background (**-28 LUFS to -32 LUFS**).

### 4.2 Visual Compositing & Blend Modes

| Visual Asset Type | Primary Blend Mode | Secondary Blend Mode | Notes |
|---|---|---|---|
| **Light Leaks / Lens Flares** | `Screen` | `Add` | Brightens underlying clip; preserves highlights. |
| **Smoke / Fire / Sparks / HUD** | `Screen` | `Add` | Requires black background or embedded Alpha channel. |
| **Film Grain / Scratches** | `Overlay` | `Soft Light` | Adds organic texture without blowing out exposure. |
| **Dust Particles / Bokeh** | `Screen` | `Add` | Soft ambient visual interest. |
| **Transitions (Matte / Glitch)** | Alpha compositing | `Screen` | Inserted exactly across the cut point (e.g. 10 frames before, 10 frames after). |

---

## 5. Technical Specifications & Compliance

- **Audio Sample Rate**: 48,000 Hz (48kHz), 16/24-bit PCM WAV or high-bitrate MP3.
- **Video Resolution**: Standard 1080p ($1920 \times 1080$) or 4K ($3840 \times 2160$).
- **Frame Rate**: Standard 24fps, 29.97fps, 30fps, or 60fps.
- **Alpha Channels**: ProRes 4444 (`yuva420p` / `rgba` / `bgra`) or WebM (`vp9` with alpha).
- **Clipping Prevention**: Audio peak levels must never exceed **-1.0 dBFS**.

---

## 6. How AI Agents Query Assets Programmatically

Instead of scanning paths manually, agents query `open_edit.asset_resolver`:

```python
from open_edit.asset_resolver import AssetResolver

resolver = AssetResolver()

# Query by natural language trigger / intent:
whoosh_asset = resolver.resolve_by_trigger("scene_transition")
# Returns asset object with file_path, category, duration, recommended blend mode & LUFS.

# Query by category & tags:
explosion_asset = resolver.resolve(category="sfx", tags=["impact", "explosion"])
```
