"""Turn template: text slides in from the left, holds, slides out."""


def turn_slide_text(params, duration_s: float) -> str:
    return f'''
from moviepy.editor import TextClip, CompositeVideoClip, ColorClip
import os

bg = ColorClip(size=(1920, 1080), color={params.background_color!r}, duration={duration_s})
text = TextClip({params.text!r}, fontsize=70, color={params.text_color!r}, size=(1600, 400))
text = (
    text.set_position(lambda t: ("left", "center"))
    .set_duration({duration_s})
    .set_start(0)
)
text = text.crossfadein(0.4).crossfadeout(0.4)
composite = CompositeVideoClip([bg, text])
composite.write_videofile(os.environ["OUTPUT_PATH"], fps=30, codec="libx264")
'''
