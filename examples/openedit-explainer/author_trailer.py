"""Generate original artwork and audio for the OpenEdit ten-second trailer.

This writes editable assets, not rendered video. create_project.py imports them
through OpenEdit; its graphics canvas and media pipeline produce the video.
"""
from __future__ import annotations

import html
import json
import math
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
DURATION = 10
BG = '#090b0e'
INK = '#f7f8f2'
LIME = '#ccff5f'
BLUE = '#659bff'
CORAL = '#ff806c'
MUTED = '#89939d'


def props(**values):
    return ' '.join(f'{k}={{{json.dumps(v)}}}' if isinstance(v, (int, float, bool))
                    else f'{k}="{html.escape(v, quote=True)}"' for k, v in values.items())


def keys(node, prop, points, ease='easeOut'):
    return f'<keyframeTrack id="{node}-{prop}" property="{prop}">' + ''.join(
        f'<keyframe id="{node}-{prop}-{i}" time={{{t}}} value={{{v}}} easing="{ease}" />'
        for i, (t, v) in enumerate(sorted(dict(points).items()))) + '</keyframeTrack>'


def r(node, x, y, w, h, color, radius=0, opacity=1, anim='', **extra):
    return f'<rect {props(id=node, x=x, y=y, width=w, height=h, fill=color, cornerRadius=radius, opacity=opacity, end=10, **extra)}>{anim}</rect>'


def text(node, content, x, y, w, size, color=INK, anim='', **extra):
    return f'<text {props(id=node, x=x, y=y, width=w, height=size * 1.45, fontFamily="OpenEdit Sans", fontSize=size, fontWeight=700, color=color, end=10, **extra)}>{html.escape(content)}{anim}</text>'


def g(node, children, x=0, y=0, anim='', **extra):
    return f'<group {props(id=node, x=x, y=y, end=10, **extra)}>{anim}{children}</group>'


def visible(node, a, b):
    return keys(node, 'opacity', [(0, 0), (a, 0), (a + .10, 1), (b - .10, 1), (b, 0), (10, 0)], 'linear')


def reveal(node, at, y):
    return keys(node, 'y', [(0, y + 120), (at, y + 120), (at + .25, y - 8), (at + .38, y)]) + keys(node, 'opacity', [(0, 0), (at, 0), (at + .12, 1)])


def star(node, x, y, size, color, at):
    shape = r(node + '-a', -size / 2, -3, size, 6, color, 3)
    shape += r(node + '-b', -3, -size / 2, 6, size, color, 3)
    return g(node, shape, x, y, keys(node, 'rotation', [(0, 0), (at, 0), (at + .65, 135), (10, 180)]) + keys(node, 'scale', [(0, 0), (at, 0), (at + .16, 1.25), (at + .35, 1), (at + 1, .45)]))


def scenery(node, w, h, kind=0, moving=True):
    """Original geometric footage, clipped inside a miniature film frame."""
    out = f'<rect id="{node}-mask" width={{{w}}} height={{{h}}} cornerRadius={{18}} clipPath />'
    out += r(node + '-sky', 0, 0, w, h, ['#19334b', '#26223c', '#263b37'][kind])
    out += r(node + '-sun', w * .70, h * .12, h * .30, h * .30, [CORAL, BLUE, LIME][kind], h,
             anim=(keys(node + '-sun', 'y', [(0, h * .17), (10, h * .10)])
                   + keys(node + '-sun', 'x', [(0, w * .73), (10, w * .63)])) if moving else '')
    if kind == 1:
        for i in range(9):
            bh = h * (.3 + .25 * math.sin(i * 2.7) ** 2)
            out += r(node + f'-building-{i}', i * w / 8 - 10, h - bh, w / 10, bh, '#111c2c', 4)
            out += r(node + f'-window-{i}', i * w / 8 + 8, h - bh + 14, 5, bh * .55, BLUE, 2)
    else:
        out += r(node + '-rear', -w * .12, h * .52, w * .8, h, '#344854', 28, rotation=-28)
        out += r(node + '-front', w * .45, h * .50, w * .9, h, '#102a2b', 28, rotation=-32)
    out += r(node + '-ground', 0, h * .80, w, h * .3, '#0d191e')
    for i in range(7):
        yy = h * (.60 + i * .063)
        ww = w * (.08 + i * .032)
        road_keys = []
        if moving:
            for j in range(13):
                at = round(j * .8, 3)
                road_keys.extend([(at, yy), (round(at + .78, 3), yy + h * .055)])
            road_keys = [(t, v) for t, v in road_keys if t <= 10]
        out += r(node + f'-road-{i}', w * .52 - ww / 2, yy, ww, 2 + i * 1.2, LIME, 2,
                 opacity=.32 + .065 * i,
                 anim=keys(node + f'-road-{i}', 'y', road_keys, 'linear') if moving else '')
    return out


def artwork():
    bg = r('background', 0, 0, 1920, 1080, BG)
    for i in range(8):
        bg += r(f'grid-{i}', 110 + i * 245, 0, 1, 1080, INK, opacity=.025)
    for i in range(6):
        bg += r(f'grid-h-{i}', 0, 110 + i * 180, 1920, 1, INK, opacity=.025)
    # Small moving technical detail grounds the energetic typography.
    bg += text('brand', 'OPENEDIT', 90, 55, 360, 25, LIME)
    bg += text('edition', 'IDEA → EDIT → SHARE', 1450, 55, 400, 20, MUTED)
    bg += r('bottom-line', 90, 1015, 1740, 2, '#24302b')
    bg += r('bottom-progress', 90, 1015, 1740, 2, LIME, anim=keys('bottom-progress', 'width', [(0, 0), (10, 1740)], 'linear'))

    # 0-1.8: a kinetic cold open; three little film frames orbit the words.
    intro = text('your', 'YOUR', 160, 175, 1250, 180, anim=reveal('your', .05, 175))
    intro += text('ideas', 'IDEAS.', 145, 350, 1500, 260, LIME, anim=reveal('ideas', .30, 350))
    intro += text('in-motion', 'PUT THEM IN MOTION.', 163, 727, 1100, 39, anim=reveal('in-motion', .7, 727))
    intro += r('intro-rule', 162, 850, 940, 8, BLUE, 4, anim=keys('intro-rule', 'width', [(0, 0), (.65, 0), (1.1, 940)]))
    for i, (x, y, rot) in enumerate([(1300, 155, 11), (1470, 452, -12), (1250, 715, 7)]):
        cid = f'orbit-{i}'
        art = r(cid + '-edge', -8, -8, 298, 184, [BLUE, CORAL, LIME][i], 25)
        art += g(cid + '-art', scenery(cid, 282, 168, i))
        intro += g(cid + '-card', art, x, y,
                   keys(cid + '-card', 'x', [(0, x + 650), (.2 + i * .10, x + 650), (.75 + i * .10, x - 20), (1.25, x), (1.7, x - 50)])
                   + keys(cid + '-card', 'rotation', [(0, rot + 45), (.9, rot), (1.7, rot - 6)])
                   + keys(cid + '-card', 'y', [(0, y + 24), (.8, y), (1.3, y - 24), (1.75, y + 5)]))
    intro += star('intro-star', 1120, 260, 75, LIME, .25)
    intro += star('intro-star-small', 1090, 790, 42, BLUE, .5)
    intro = g('intro', intro, anim=visible('intro', 0, 1.85) + keys('intro', 'x', [(0, 0), (1.65, 0), (1.85, -160)]))

    # 1.6-4.15: actual product idea: select a moment and describe the edit.
    direct = text('say-just', 'JUST', 100, 220, 650, 146, anim=reveal('say-just', 1.65, 220))
    direct += text('say-it', 'SAY IT.', 100, 390, 670, 146, LIME, anim=reveal('say-it', 1.83, 390))
    direct += text('say-copy', 'Your agent. Your direction.', 108, 615, 670, 31, MUTED)
    app = r('app-outline', -3, -3, 974, 707, '#3c474a', 25)
    app += r('app-back', 0, 0, 968, 701, '#14191c', 24)
    app += r('app-dot', 23, 25, 10, 10, LIME, 5)
    app += text('app-label', 'OPENEDIT / LIVE PREVIEW', 48, 17, 710, 18, MUTED)
    app += g('hero-footage', scenery('hero', 910, 351, 0), 29, 63)
    app += r('cinema-top', 29, 63, 910, 36, BG, anim=keys('cinema-top', 'height', [(0, 0), (2.95, 0), (3.3, 36)]))
    app += r('cinema-bottom', 29, 378, 910, 36, BG, anim=keys('cinema-bottom', 'height', [(0, 0), (2.95, 0), (3.3, 36)]))
    app += r('scan-glow', 29, 63, 16, 351, LIME, opacity=.22, anim=keys('scan-glow', 'x', [(0, 29), (2.7, 29), (3.25, 923)]) + keys('scan-glow', 'opacity', [(0, 0), (2.7, 0), (2.75, .5), (3.25, .5), (3.3, 0)]))
    app += r('prompt-back', 55, 340, 858, 105, INK, 19, anim=reveal('prompt-back', 2.15, 340))
    app += text('prompt-text', 'Make it cinematic.', 84, 361, 750, 43, BG, anim=reveal('prompt-text', 2.2, 361))
    app += r('send-bg', 834, 361, 56, 56, BG, 15, anim=keys('send-bg', 'opacity', [(0, 0), (2.45, 0), (2.6, 1)]))
    app += text('send', '↑', 850, 360, 45, 37, LIME, anim=keys('send', 'opacity', [(0, 0), (2.45, 0), (2.6, 1)]))
    app += text('region-label', 'SELECTED MOMENT', 31, 465, 560, 17, MUTED)
    for i, (x, w, col) in enumerate([(29, 270, BLUE), (309, 330, LIME), (649, 290, CORAL)]):
        app += r(f'app-clip-{i}', x, 511, w, 67, col, 10)
        app += text(f'app-time-{i}', ['00:00', '00:04.20', '00:07'][i], x + 15, 534, w - 20, 17, BG)
    app += r('region-top', 305, 500, 338, 3, INK, anim=keys('region-top', 'width', [(0, 0), (2.1, 0), (2.35, 338)]))
    app += r('region-bottom', 305, 582, 338, 3, INK, anim=keys('region-bottom', 'width', [(0, 0), (2.1, 0), (2.35, 338)]))
    app += r('app-playhead', 320, 490, 3, 108, INK, anim=keys('app-playhead', 'x', [(0, 320), (2.3, 320), (3.95, 630)], 'linear'))
    app += text('applied', '✓  EDIT APPLIED', 34, 623, 650, 22, LIME, anim=keys('applied', 'opacity', [(0, 0), (3.2, 0), (3.35, 1)]))
    direct += g('app-window', app, 815, 195, keys('app-window', 'y', [(0, 380), (1.65, 380), (2.05, 185), (2.3, 195), (3.95, 184)]) + keys('app-window', 'rotation', [(0, 5), (1.65, 5), (2.3, 0), (3.95, -1)]))
    direct += star('direct-star', 726, 771, 72, BLUE, 2.85)
    direct = g('direct', direct, anim=visible('direct', 1.65, 4.16))

    # 4-6.55: magnetized cards, animated waveforms, a precise traveling playhead.
    flow = text('flow-title', 'LET IT', 110, 125, 850, 118, anim=reveal('flow-title', 4.0, 125))
    flow += text('flow-word', 'FLOW.', 600, 120, 1100, 140, LIME, anim=reveal('flow-word', 4.16, 120))
    flow += text('flow-copy', 'CUT.  MOVE.  ANIMATE.', 115, 320, 1200, 28, MUTED)
    for i in range(3):
        cid = f'flow-card-{i}'
        card = r(cid + '-shell', -7, -7, 522, 256, [LIME, BLUE, CORAL][i], 23)
        card += g(cid + '-picture', scenery(cid, 508, 205, (i + 2) % 3))
        card += r(cid + '-label-bg', 0, 198, 508, 44, '#182022', 0)
        card += text(cid + '-caption', ['01 / THE HOOK', '02 / THE MOMENT', '03 / THE STORY'][i], 18, 207, 475, 18, INK)
        target = 120 + i * 570
        flow += g(cid, card, target, 460,
                  keys(cid, 'x', [(0, [1250, -650, 2200][i]), (4.03 + i * .10, [1250, -650, 2200][i]), (4.62 + i * .10, target + 14), (4.82 + i * .10, target)])
                  + keys(cid, 'y', [(0, 460 + i * 70), (4.08, 460 + i * 70), (4.85, 450), (5.2, 460), (5.6, 448 + i * 3), (6.0, 460), (6.5, 448 + i * 3)])
                  + keys(cid, 'rotation', [(0, [17, -19, 15][i]), (4.10, [17, -19, 15][i]), (4.85, 0), (6.4, 0)]))
    flow += r('track-bg', 108, 780, 1704, 141, '#182021', 18)
    for i, (x, w, col) in enumerate([(125, 502, LIME), (639, 532, BLUE), (1183, 610, CORAL)]):
        flow += r(f'flow-block-{i}', x, 797, w, 42, col, 8, anim=keys(f'flow-block-{i}', 'width', [(0, 0), (4.60 + i * .12, 0), (4.9 + i * .12, w)]))
    for i in range(38):
        hh = 9 + 35 * abs(math.sin(i * 1.73))
        nid = f'wave-{i}'
        flow += r(nid, 137 + i * 43, 869 - hh / 2, 13, hh, LIME, 4,
                  anim=keys(nid, 'height', [(0, hh), (4.7, hh), (5.0, hh * .45), (5.25, hh), (5.5, hh * .5), (5.75, hh), (6.0, hh * .65), (6.25, hh)]))
    flow += r('flow-head', 124, 767, 4, 169, INK, anim=keys('flow-head', 'x', [(0, 124), (4.95, 124), (6.35, 1788)], 'linear'))
    flow += text('live-tag', '● LIVE PREVIEW', 1445, 322, 380, 23, LIME)
    flow += star('flow-spark', 1705, 180, 55, CORAL, 4.7)
    flow = g('flow', flow, anim=visible('flow', 4.0, 6.56))

    # 6.4-8.15: export as a tangible final film card and a quick progress beat.
    share = text('ready-title', 'READY', 108, 230, 870, 144, anim=reveal('ready-title', 6.4, 230))
    share += text('share-title', 'TO SHARE.', 108, 390, 1080, 128, LIME, anim=reveal('share-title', 6.52, 390))
    share += text('export-detail', '1080p  /  60 FPS  /  YOUR STORY', 115, 647, 1050, 26, MUTED)
    film = r('export-card-border', -8, -8, 686, 437, LIME, 26)
    film += g('export-card-art', scenery('export-art', 670, 421, 2))
    film += r('play-box', 265, 145, 140, 140, INK, 35)
    # Literal geometry avoids platform-specific color-emoji play-button glyphs.
    for i in range(18):
        height = 76 * (1 - i / 18)
        film += r(f'play-triangle-{i}', 310 + i * 3.1, 215 - height / 2, 5.5, height, BG)
    share += g('export-card', film, 1120, 285,
               keys('export-card', 'x', [(0, 2160), (6.4, 2160), (6.82, 1100), (7.0, 1120)])
               + keys('export-card', 'rotation', [(0, 15), (6.4, 15), (7.0, -4), (8.0, 2)]))
    share += r('export-rail', 115, 772, 880, 14, '#29332c', 7)
    share += r('export-fill', 115, 772, 880, 14, LIME, 7, anim=keys('export-fill', 'width', [(0, 0), (6.75, 0), (7.55, 880)], 'easeInOut'))
    share += text('export-success', '✓  GOOD TO GO.', 118, 820, 850, 28, LIME, anim=keys('export-success', 'opacity', [(0, 0), (7.55, 0), (7.65, 1)]))
    share += star('export-spark', 1760, 217, 75, BLUE, 6.75)
    share = g('share', share, anim=visible('share', 6.4, 8.17))

    # 8-10: burst particles settle around the brand, rather than a static slide.
    finish = ''
    for i in range(18):
        angle = i * math.tau / 18
        x = 960 + math.cos(angle) * 740
        y = 485 + math.sin(angle) * 350
        pid = f'burst-{i}'
        finish += r(pid, x, y, 28 if i % 3 else 58, 5, [LIME, BLUE, CORAL][i % 3], 3,
                    rotation=i * 20,
                    anim=keys(pid, 'x', [(0, 960), (8.02, 960), (8.45, x), (10, x + math.cos(angle) * 80)])
                    + keys(pid, 'y', [(0, 485), (8.02, 485), (8.45, y), (10, y + math.sin(angle) * 50)])
                    + keys(pid, 'opacity', [(0, 0), (8.02, 0), (8.10, 1), (8.7, .20), (10, .06)]))
    logo = r('logo-base', 0, 0, 168, 168, LIME, 36)
    for i, (yy, ww) in enumerate([(37, 108), (76, 68), (115, 92)]):
        logo += r(f'logo-bar-{i}', 30, yy, ww, 18, BG, 6,
                  anim=keys(f'logo-bar-{i}', 'x', [(0, -240), (8.05 + i * .06, -240), (8.38 + i * .06, 36), (8.55 + i * .06, 30)]))
    finish += g('logo', logo, 370, 346, keys('logo', 'rotation', [(0, -28), (8.02, -28), (8.32, 5), (8.5, 0)]))
    finish += text('wordmark', 'OpenEdit', 588, 312, 1160, 162, anim=reveal('wordmark', 8.05, 312))
    finish += text('tagline', 'Think it. Edit it.', 594, 533, 1160, 66, LIME, anim=reveal('tagline', 8.26, 533))
    finish += r('final-pill', 590, 712, 775, 73, '#1c2620', 36, anim=keys('final-pill', 'opacity', [(0, 0), (8.7, 0), (8.9, 1)]))
    finish += text('final-description', 'YOUR AI-NATIVE VIDEO EDITOR', 630, 730, 760, 25, INK, anim=keys('final-description', 'opacity', [(0, 0), (8.7, 0), (8.9, 1)]))
    finish += star('finish-star', 1550, 618, 57, BLUE, 8.35)
    finish = g('finish', finish, anim=keys('finish', 'opacity', [(0, 0), (8.0, 0), (8.09, 1)]))

    # Brief colored wipes mask scene handoffs, with matching stereo whooshes.
    wipes = ''
    for i, at in enumerate([1.68, 4.03, 6.43, 8.03]):
        wid = f'wipe-{i}'
        wipes += r(wid, -2400, 0, 2100, 1080, [LIME, BLUE, CORAL, LIME][i], anim=keys(wid, 'x', [(0, -2400), (at - .13, -2400), (at, -1900), (at + .12, 1920), (10, 1920)], 'linear'))
    return 'export default function OpenEditTrailer() { return <stage id="openedit-explainer"><scene id="main" width={1920} height={1080} active>\n' + '\n'.join([bg, intro, direct, flow, share, finish, wipes]) + '\n</scene></stage>; }\n'


def soundtrack():
    """Deterministic original electro score + stereo foley, separately editable."""
    sr = 48000
    rng = np.random.default_rng(6414)
    music = np.zeros((sr * DURATION, 2))
    effects = np.zeros_like(music)
    cues = []

    def add(target, at, signal, gain=1, pan=0):
        start = round(at * sr)
        count = min(len(signal), len(target) - start)
        if count <= 0:
            return
        target[start:start + count, 0] += signal[:count] * gain * math.sqrt((1 - pan) / 2)
        target[start:start + count, 1] += signal[:count] * gain * math.sqrt((1 + pan) / 2)

    def tone(at, hz, dur, gain, pan=0, target=music, bright=.25):
        t = np.arange(round(dur * sr)) / sr
        env = (1 - np.exp(-t * 220)) * np.exp(-t * 5 / dur) * np.minimum(1, (dur - t) / .035)
        sig = (np.sin(2 * np.pi * hz * t) + bright * np.sin(4 * np.pi * hz * t) + .07 * np.sin(6 * np.pi * hz * t)) * env
        add(target, at, sig, gain, pan)

    # 150 BPM; a punchy but uncluttered beat and a minor-nine melodic pattern.
    for beat in range(20):
        at = .05 + beat * .4
        t = np.arange(round(.26 * sr)) / sr
        phase = 2 * np.pi * (48 * t + 100 * .022 * (1 - np.exp(-t / .022)))
        kick = np.sin(phase) * np.exp(-t * 18) * (1 - np.exp(-t * 800))
        add(music, at, kick, .57)
        bass = [65.406, 65.406, 77.782, 58.270][beat // 5 % 4]
        tone(at + .055, bass, .33, .19, bright=.45)
        if beat % 2 == 1:
            t = np.arange(round(.13 * sr)) / sr
            noise = rng.normal(size=len(t))
            clap = (noise - np.convolve(noise, np.ones(9) / 9, mode='same')) * np.exp(-t * 35)
            add(music, at, clap, .13)
        for off in [.0, .2]:
            t = np.arange(round(.055 * sr)) / sr
            noise = rng.normal(size=len(t))
            hat = (noise - np.convolve(noise, np.ones(5) / 5, mode='same')) * np.exp(-t * 95)
            add(music, at + off, hat, .042, .35 if beat % 2 else -.35)
    for i in range(40):
        hz = [261.626, 391.995, 466.164, 587.330, 523.251, 391.995, 311.127, 466.164][i % 8]
        tone(.12 + i * .2, hz, .28, .078, math.sin(i * 1.7) * .55)

    def whoosh(at, dur=.37, direction=1):
        t = np.arange(round(dur * sr)) / sr
        noise = rng.normal(size=len(t))
        spectrum = np.fft.rfft(noise)
        freq = np.fft.rfftfreq(len(noise), 1 / sr)
        spectrum *= np.exp(-((freq - 1800) / 1600) ** 2)
        sig = np.fft.irfft(spectrum, n=len(t)) * np.sin(np.pi * t / dur) ** 1.5
        sig += .12 * np.sin(2 * np.pi * (160 * t + 1000 * t * t / dur)) * np.sin(np.pi * t / dur) ** 2
        start = round(at * sr)
        pan = np.linspace(-.8 * direction, .8 * direction, len(sig))
        effects[start:start + len(sig), 0] += sig * .25 * np.sqrt((1 - pan) / 2)
        effects[start:start + len(sig), 1] += sig * .25 * np.sqrt((1 + pan) / 2)
        cues.append({'time': at, 'effect': 'stereo sweep', 'duration': dur})

    def hit(at, weight=.45):
        t = np.arange(round(.52 * sr)) / sr
        sub = np.sin(2 * np.pi * (46 * t + 55 * .035 * (1 - np.exp(-t / .035)))) * np.exp(-t * 12)
        click = rng.normal(size=len(t)) * np.exp(-t * 110)
        add(effects, at, sub + click * .22, weight)
        cues.append({'time': at, 'effect': 'low impact + transient'})

    for at, direction in [(1.53, 1), (3.88, -1), (6.28, 1), (7.88, -1)]:
        whoosh(at, .37, direction)
    for at in [.13, .43, 1.8, 4.17, 6.57, 8.12]:
        hit(at, .65 if at == 8.12 else .28)
    for i, at in enumerate([.74, .84, .94, 2.35, 2.6, 3.3, 4.62, 4.74, 4.86, 7.58]):
        tone(at, [1174.66, 1567.98, 2093.00][i % 3], .085, .07, (-1) ** i * .45, effects, .1)
        cues.append({'time': at, 'effect': 'magnetic snap / UI tick'})
    # Successful export has a rising three-note chime; brand lands on a warm chord.
    for i, hz in enumerate([523.251, 783.991, 1046.502]):
        tone(7.55 + i * .055, hz, .45, .10, -.2 + i * .2, effects)
    for hz in [130.813, 261.626, 311.127, 391.995, 587.330]:
        tone(8.12, hz, 1.85, .14 if hz < 200 else .08, target=music)
    # Stereo short reflections supply depth without masking the sharp cuts.
    for delay, amount in [(.073, .15), (.147, .09), (.219, .05)]:
        n = round(delay * sr)
        effects[n:] += effects[:-n, ::-1] * amount
    combined = music + effects
    scale = .87 / np.max(np.abs(combined))
    music *= scale
    effects *= scale
    fade = np.minimum(1, np.arange(len(music)) / (sr * .015))
    fade *= np.minimum(1, (len(music) - 1 - np.arange(len(music))) / (sr * .26))
    music *= fade[:, None]
    effects *= fade[:, None]

    def write(name, data):
        with wave.open(str(ROOT / name), 'wb') as handle:
            handle.setnchannels(2)
            handle.setsampwidth(2)
            handle.setframerate(sr)
            handle.writeframes(np.clip(data * 32767, -32768, 32767).astype('<i2').tobytes())
    write('music.wav', music)
    write('sound-effects.wav', effects)
    write('score.wav', music + effects)
    (ROOT / 'sound-cues.json').write_text(json.dumps(sorted(cues, key=lambda x: x['time']), indent=2) + '\n')
    return {'peak': float(np.max(np.abs(music + effects))), 'sample_rate': sr, 'duration_sec': DURATION}


if __name__ == '__main__':
    source = artwork()
    (ROOT / 'scene.jsx').write_text(source, encoding='utf-8')
    print(json.dumps({'source_bytes': len(source.encode()), 'audio': soundtrack()}, indent=2))
