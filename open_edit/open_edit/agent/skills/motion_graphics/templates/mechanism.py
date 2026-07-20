"""Mechanism template: text shown in a labeled diagram box (v1: simple
rectangle + label). v1.1 can layer in a real diagram generator.
"""


def mechanism_diagram(params, duration_s: float) -> str:
    return f'''
from moviepy.editor import TextClip, CompositeVideoClip, ColorClip
import os

bg = ColorClip(size=(1920, 1080), color={params.background_color!r}, duration={duration_s})
label = TextClip({params.text!r}, fontsize=72, color={params.text_color!r}, size=(1400, 400))
box = (
    ColorClip(size=(1500, 450), color=(1, 1, 1), duration={duration_s})
    .set_opacity(0.12)
    .set_position("center")
)
label = label.set_position("center").set_duration({duration_s})
composite = CompositeVideoClip([bg, box, label])
composite.write_videofile(os.environ["OUTPUT_PATH"], fps=30, codec="libx264")
'''
