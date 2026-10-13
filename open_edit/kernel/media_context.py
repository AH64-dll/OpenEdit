"""Small, timestamped visual references and range transcripts from immutable media."""
from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from pathlib import Path

from open_edit.render.asset_visuals import _LOCKS, _run
from open_edit.storage.assets import AssetStore
from open_edit.storage.transcription import pack_transcript


def query_image(result: dict, arguments: dict, project_path: Path) -> dict | None:
    """Attach only explicit visual query outputs below this project's data root."""
    if arguments.get('query') not in {'inspect_media', 'get_timeline_view'} or result.get('status') != 'ok':
        return None
    if not result.get('image_path'):
        return None
    path = Path(result['image_path']).resolve()
    if not path.is_relative_to((project_path / '.open_edit').resolve()) or not path.is_file():
        return None
    if path.stat().st_size > 4 * 1024 * 1024:
        return None
    import base64

    return {'type': 'image', 'data': base64.b64encode(path.read_bytes()).decode(),
            'mimeType': 'image/png' if path.suffix == '.png' else 'image/jpeg'}


def inspect_media(project_path: Path, *, asset_hash: str, start_sec: float = 0,
                  end_sec: float | None = None, frames: int = 4,
                  transcript_limit: int = 120, word_offset: int = 0) -> dict:
    """Retrieve a bounded time range. Zero frames makes a transcript-only request.

    Sample times are source seconds, not timeline seconds. Narrow the range or
    increase frames to resolve a specific event; samples do not establish scene
    boundaries or describe visual content without a vision-capable model.
    """
    import re

    if not re.fullmatch(r'[a-f0-9]{64}', asset_hash):
        raise ValueError('Invalid asset hash')
    if type(frames) is not int or not 0 <= frames <= 12:
        raise ValueError('frames must be an integer between 0 and 12')
    if type(transcript_limit) is not int or not 0 <= transcript_limit <= 500:
        raise ValueError('transcript_limit must be an integer between 0 and 500')
    if type(word_offset) is not int or word_offset < 0:
        raise ValueError('word_offset must be a nonnegative integer')
    store = AssetStore(project_path / '.open_edit/assets')
    asset, source = store.get(asset_hash), store.path(asset_hash)
    if not asset or not source:
        raise ValueError('Project media is unavailable')
    end_sec = asset.duration_sec if end_sec is None else end_sec
    if any(isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t)
           for t in (start_sec, end_sec)):
        raise ValueError('Range must use finite source seconds')
    if asset.type != 'image' and not 0 <= start_sec < end_sec <= asset.duration_sec + 1e-6:
        raise ValueError('Range must lie within the source duration')
    if asset.type == 'image' and start_sec != 0:
        raise ValueError('Images have no time range')
    words = [w for w in asset.alignment if w.t_end > start_sec and w.t_start < end_sec]
    page = words[word_offset:word_offset + transcript_limit]
    result = {
        'status': 'ok', 'asset_hash': asset_hash, 'filename': Path(asset.original_path).name,
        'source_range': {'start_sec': start_sec, 'end_sec': end_sec},
        'duration_sec': asset.duration_sec, 'size': [asset.width, asset.height],
        'fps': asset.fps, 'frames': [],
        'transcript': {'text': pack_transcript(page), 'range_words': len(words),
                       'returned_words': len(page), 'offset': word_offset,
                       'next_offset': word_offset + len(page) if transcript_limit and
                       word_offset + len(page) < len(words) else None,
                       'available': bool(asset.alignment)},
    }
    count = 0 if asset.type == 'audio' else min(frames, 1) if asset.type == 'image' else frames
    if not count:
        return result
    # Never seek to EOF; hold the final decodable frame instead.
    last = max(start_sec, end_sec - 1 / (asset.fps or 30))
    times = [round(start_sec + (last - start_sec) * i / max(1, count - 1), 6)
             for i in range(count)]
    key = hashlib.sha256(json.dumps([1, asset_hash, times]).encode()).hexdigest()
    cache = project_path / '.open_edit/cache/media-context' / asset_hash
    output = cache / f'{key}.jpg'
    with _LOCKS[int(asset_hash[:2], 16) % len(_LOCKS)]:
        hit = output.is_file()
        if not hit:
            from PIL import Image, ImageDraw

            cache.mkdir(parents=True, exist_ok=True)
            columns = min(3, count)
            sheet = Image.new('RGB', (columns * 320, math.ceil(count / columns) * 204), '#12161d')
            draw = ImageDraw.Draw(sheet)
            with tempfile.TemporaryDirectory(dir=cache) as scratch_dir:
                scratch = Path(scratch_dir)
                for i, time in enumerate(times):
                    frame = scratch / f'{i}.jpg'
                    _run(['-ss', str(time), '-i', str(source), '-frames:v', '1', '-vf',
                          'scale=320:180:force_original_aspect_ratio=decrease,pad=320:180:(ow-iw)/2:(oh-ih)/2',
                          '-q:v', '4', str(frame)], timeout=30)
                    x, y = (i % columns) * 320, (i // columns) * 204
                    with Image.open(frame) as image:
                        sheet.paste(image, (x, y))
                    draw.text((x + 8, y + 185), f'{time:.3f}s', fill='white')
                pending = scratch / 'sheet.jpg'
                sheet.save(pending, quality=85)
                os.replace(pending, output)
            # Range exploration must not create an unbounded secondary cache.
            for stale in sorted(cache.glob('*.jpg'), key=lambda p: p.stat().st_mtime, reverse=True)[64:]:
                if stale != output:
                    stale.unlink(missing_ok=True)
    result.update(image_path=str(output), cache_hit=hit,
                  frames=[{'index': i, 'source_sec': time} for i, time in enumerate(times)])
    return result
