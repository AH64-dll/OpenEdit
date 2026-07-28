"""Cost template: warning-style text on a dark background, mild pulse."""


def cost_warning(params, duration_s: float) -> str:
    return f'''
from moviepy.editor import TextClip, CompositeVideoClip, ColorClip
import os

bg = ColorClip(size=(1920, 1080), color={params.background_color!r}, duration={duration_s})
text = TextClip({params.text!r}, fontsize=90, color={params.text_color!r}, size=(1600, 500))


def _pulse(t):
    import math
    return 0.85 + 0.15 * math.sin(2 * math.pi * t * 1.5)


text = (
    text.resize(_pulse)
    .set_position("center")
    .set_duration({duration_s})
)
composite = CompositeVideoClip([bg, text])
composite.write_videofile(os.environ["OUTPUT_PATH"], fps=30, codec="libx264")
'''
