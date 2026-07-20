"""Scope template: text zooms in from small to large."""


def scope_zoom_text(params, duration_s: float) -> str:
    return f'''
from moviepy.editor import TextClip, CompositeVideoClip, ColorClip
import os

bg = ColorClip(size=(1920, 1080), color={params.background_color!r}, duration={duration_s})
text = TextClip({params.text!r}, fontsize=80, color={params.text_color!r}, size=(1600, 400))


def _zoom(t, base=0.6, peak=1.0):
    half = max({duration_s} / 2.0, 0.01)
    if t < half:
        return base + (peak - base) * (t / half)
    return peak


text = (
    text.resize(_zoom)
    .set_position("center")
    .set_duration({duration_s})
)
composite = CompositeVideoClip([bg, text])
composite.write_videofile(os.environ["OUTPUT_PATH"], fps=30, codec="libx264")
'''
