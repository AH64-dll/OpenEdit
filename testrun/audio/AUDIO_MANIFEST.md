# AUDIO_MANIFEST

Generated with **ffmpeg n8.1.2** using ONLY lavfi sources (no downloads, no external samples).
All files: WAV PCM s16le, 44.1 kHz sample rate. Output dir: `/home/amr/apps/mlt-pipeline/testrun/audio/`

| file | duration | sample rate | channels | codec |
|---|---|---|---|---|
| music_bed.wav | 40.000 s | 44100 Hz | 2 (stereo) | pcm_s16le |
| whoosh.wav | 1.000 s | 44100 Hz | 1 (mono) | pcm_s16le |
| pop.wav | 0.150 s | 44100 Hz | 1 (mono) | pcm_s16le |
| riser.wav | 2.000 s | 44100 Hz | 1 (mono) | pcm_s16le |
| tone_test.wav | 2.000 s | 44100 Hz | 1 (mono) | pcm_s16le |

Verified with ffprobe (`codec_name`, `sample_rate`, `channels`, `format.duration`). Levels via volumedetect: music_bed mean -19.2 dB / max -4.5 dB; whoosh mean -14.9 / max -1.5; pop mean -10.6 / max -2.0; riser mean -14.9 / max -4.9; tone_test max -12.0 dB (exact reference). No clipping anywhere.

## 1. music_bed.wav — 40 s gentle cinematic pad (A minor: A2/C3/E3/A3 + air noise)

Layered Aevalsrc sines + white-noise air, amixed, slow tremolo + volume LFO, lowpass, fades, limiter.

```bash
ffmpeg -y -v error \
  -f lavfi -i "aevalsrc='0.25*sin(2*PI*110*t)':d=40:s=44100" \
  -f lavfi -i "aevalsrc='0.22*sin(2*PI*130.81*t)':d=40:s=44100" \
  -f lavfi -i "aevalsrc='0.19*sin(2*PI*164.81*t)':d=40:s=44100" \
  -f lavfi -i "aevalsrc='0.16*sin(2*PI*220*t)':d=40:s=44100" \
  -f lavfi -i "anoisesrc=color=white:duration=40:sample_rate=44100:amplitude=0.12" \
  -filter_complex "[4]highpass=f=3500,lowpass=f=11000,volume=0.5[air];[0][1][2][3][air]amix=inputs=5:normalize=0[mix];[mix]tremolo=f=0.3:d=0.9,volume='0.75+0.25*sin(2*PI*0.1*t)':eval=frame,lowpass=f=3800,afade=t=in:st=0:d=1.5,afade=t=out:st=38:d=2,alimiter=limit=0.89[out]" \
  -map "[out]" -ar 44100 -ac 2 -c:a pcm_s16le music_bed.wav
```

Key expression: `amix(inputs=5, normalize=0)` -> `tremolo=f=0.3:d=0.9` -> `volume='0.75+0.25*sin(2*PI*0.1*t)':eval=frame` -> `lowpass=f=3800` -> fades -> `alimiter=limit=0.89`.

## 2. whoosh.wav — 1.0 s transition whoosh

White noise with rising-then-falling envelope (`volume='min(1,abs(sin(t*PI)))':eval=frame`), softened with highpass/lowpass.

```bash
ffmpeg -y -v error -f lavfi -i "anoisesrc=color=white:duration=1:sample_rate=44100:amplitude=0.9" \
  -af "volume='min(1,abs(sin(t*PI)))':eval=frame,highpass=f=150,lowpass=f=5200" \
  -ar 44100 -ac 1 -c:a pcm_s16le whoosh.wav
```

## 3. pop.wav — 0.15 s UI pop

Pitch-drop sine burst (800 Hz -> ~620 Hz over 0.15 s) with exponential decay, scaled 0.8 for headroom.

```bash
ffmpeg -y -v error -f lavfi \
  -i "aevalsrc='0.8*sin(2*PI*(800-600*t)*t)*exp(-12*t)':d=0.15:s=44100" \
  -ar 44100 -ac 1 -c:a pcm_s16le pop.wav
```

Expression: `0.8*sin(2*PI*(800-600*t)*t)*exp(-12*t)` (t in seconds).

## 4. riser.wav — 2.0 s riser

Rising-pitch sine sweep (150 Hz -> ~1850 Hz) + pink noise, both volume-ramped `0.22*t` (eval=frame), summed and lowpassed. Ramp coefficient 0.22 keeps summed peak below 0 dBFS (0.22*2*(1+0.7) ~ 0.75).

```bash
ffmpeg -y -v error \
  -f lavfi -i "aevalsrc='sin(2*PI*(150+425*t)*t)':d=2:s=44100" \
  -f lavfi -i "anoisesrc=color=pink:duration=2:sample_rate=44100:amplitude=0.7" \
  -filter_complex "[0]volume='0.22*t':eval=frame[s];[1]volume='0.22*t':eval=frame[n];[s][n]amix=inputs=2:normalize=0,lowpass=f=6000" \
  -ar 44100 -ac 1 -c:a pcm_s16le riser.wav
```

## 5. tone_test.wav — 2.0 s 440 Hz reference at exactly -12 dBFS

Aevalsrc sine with amplitude 0.251189 = 10^(-12/20). (Note: lavfi `sine` source in this ffmpeg build outputs at ~-18 dBFS by default, so aevalsrc is used for the exact level.)

```bash
ffmpeg -y -v error -f lavfi \
  -i "aevalsrc='0.251189*sin(2*PI*440*t)':d=2:s=44100" \
  -ar 44100 -ac 1 -c:a pcm_s16le tone_test.wav
```

## Reproduction notes

- All sources are pure lavfi (`aevalsrc`, `anoisesrc`, `sine`); no downloads, no external samples.
- `volume` time-varying expressions use `eval=frame` (per-frame evaluation of `t`).
- `amix` always uses `normalize=0` so the specified per-layer gains are preserved exactly.
- Compute time: all files generated in well under 1 minute total on this machine.
