"""Hook template: fade-in text on a colored background.

The render sandbox (W2) executes the generated moviepy code; the output
path is provided via the ``OUTPUT_PATH`` env var by the Rust binary.
"""


def hook_fade_text(params, duration_s: float) -> str:
    return f'''
from moviepy.editor import TextClip, CompositeVideoClip, ColorClip
import os

bg = ColorClip(size=(1920, 1080), color={params.background_color!r}, duration={duration_s})
text = TextClip({params.text!r}, fontsize=80, color={params.text_color!r}, size=(1600, 400))
text = text.set_position("center").set_duration({duration_s}).fadein(0.5).fadeout(0.5)
composite = CompositeVideoClip([bg, text])
composite.write_videofile(os.environ["OUTPUT_PATH"], fps=30, codec="libx264")
'''
