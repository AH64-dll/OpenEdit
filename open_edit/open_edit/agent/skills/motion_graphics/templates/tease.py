"""Tease template: text fades in and out, partial reveal."""


def tease_glimpse(params, duration_s: float) -> str:
    return f'''
from moviepy.editor import TextClip, CompositeVideoClip, ColorClip
import os

bg = ColorClip(size=(1920, 1080), color={params.background_color!r}, duration={duration_s})
text = TextClip({params.text!r}, fontsize=78, color={params.text_color!r}, size=(1500, 400))
hold = max({duration_s} - 0.8, 0.0)
text = (
    text.set_position("center")
    .set_duration(hold)
    .fadein(0.3)
    .fadeout(0.3)
)
composite = CompositeVideoClip([bg, text])
composite.write_videofile(os.environ["OUTPUT_PATH"], fps=30, codec="libx264")
'''
