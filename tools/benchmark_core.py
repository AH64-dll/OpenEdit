"""Reproducible local media/edit/preview/export measurements, without a provider.

Run from the checkout: python tools/benchmark_core.py --output /tmp/core-metrics.json
The synthetic color/tone fixture has known source times. Transcript metadata is
ground truth supplied by this benchmark, not a transcription accuracy result.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import tempfile
import time
from pathlib import Path

from open_edit.ir.types import AddClipOp, TrimClipOp, WordAlignment
from open_edit.kernel.export_service import ExportSettings, capture_export
from open_edit.kernel.media_context import inspect_media
from open_edit.kernel.render_jobs import RenderJobService
from open_edit.kernel.studio_service import commit_studio
from open_edit.kernel.tool_registry import build_tool_schemas
from open_edit.mcp.skills import mcp_instructions
from open_edit.storage.assets import AssetStore
from open_edit.storage.edit_graph import EditGraphStore


def timed(fn):
    start = time.perf_counter()
    result = fn()
    return result, round(time.perf_counter() - start, 4)


async def benchmark() -> dict:
    report = {'tool_schema_chars': len(json.dumps(build_tool_schemas())),
              'mcp_instruction_chars': len(mcp_instructions()),
              'fixture': '4s red/blue video with 440Hz audio, repeated into an 8s timeline'}
    with tempfile.TemporaryDirectory(prefix='openedit-core-') as directory:
        root = Path(directory)
        source = root / 'source.mp4'
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi', '-i',
                        'color=red:s=640x360:r=30:d=2', '-f', 'lavfi', '-i',
                        'color=blue:s=640x360:r=30:d=2', '-f', 'lavfi', '-i',
                        'sine=frequency=440:sample_rate=48000:duration=4', '-filter_complex',
                        '[0:v][1:v]concat=n=2:v=1:a=0[v]', '-map', '[v]', '-map', '2:a',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(source)], check=True)
        assets = AssetStore(root / '.open_edit/assets')
        asset, report['ingest_sec'] = timed(lambda: assets.ingest(str(source), transcribe=False))
        assets.update_alignment(asset.asset_hash, [WordAlignment(word=f'word{i}', t_start=i / 10,
                                                                  t_end=(i + 1) / 10) for i in range(40)])
        context, report['media_cold_sec'] = timed(lambda: inspect_media(root, asset_hash=asset.asset_hash))
        cached, report['media_cached_sec'] = timed(lambda: inspect_media(root, asset_hash=asset.asset_hash))
        assert cached['cache_hit']
        from PIL import Image

        with Image.open(context['image_path']) as sheet:
            assert sheet.getpixel((160, 90))[0] > 200
            assert sheet.getpixel((800, 90))[2] > 200
        focused = inspect_media(root, asset_hash=asset.asset_hash, frames=0,
                                start_sec=2, end_sec=3, transcript_limit=10)
        report['range_transcript_words'] = focused['transcript']['returned_words']
        report['whole_transcript_words'] = context['transcript']['returned_words']
        store = EditGraphStore(root / '.open_edit/edit_graph.db')
        commit_studio(root, expected_revision=0, changes=[], label='Import two clips', ops=[
            AddClipOp(author='user', clip_id='a', asset_hash=asset.asset_hash, track_id='v1', position_sec=0,
                      out_point_sec=4).model_dump(mode='json'),
            AddClipOp(author='user', clip_id='b', asset_hash=asset.asset_hash, track_id='v1', position_sec=4,
                      out_point_sec=4).model_dump(mode='json'),
        ])
        service = RenderJobService(timeout_s=180)

        async def preview(name, ranges):
            start = time.perf_counter()
            job = service.enqueue('benchmark', root, 'preview-chunks', expected_revision=store.graph_revision(),
                                  params={'ranges': ranges, 'media': 'both', 'encoder': 'cpu'})
            complete = await service.wait(root, job.job_id)
            assert complete.status == 'succeeded', complete.error
            report[name] = {'sec': round(time.perf_counter() - start, 4),
                            'diagnostics': complete.result['diagnostics']}
            return complete

        await preview('focused_preview', [{'start_sec': 0, 'end_sec': 2}])
        filled = await preview('remaining_preview', [])
        assert filled.result['red_chunks'] == 0 and filled.result['yellow_chunks'] == 0
        warm = await preview('cached_preview', [])
        assert warm.result['diagnostics']['counts']['processed_chunks'] == 0
        revision = store.graph_revision()
        commit_studio(root, expected_revision=revision, changes=[], label='Trim first clip', ops=[
            TrimClipOp(author='user', clip_id='a', new_in_point_sec=.25, new_out_point_sec=4).model_dump(mode='json')])
        partial = await preview('edited_preview', [])
        counts = partial.result['diagnostics']['counts']
        assert counts['processed_chunks'] < counts['total_chunks'], counts
        reopened = EditGraphStore(root / '.open_edit/edit_graph.db')
        assert reopened.graph_revision() == store.graph_revision() and reopened.history()['undo']
        revision = store.graph_revision()
        payload = capture_export(root, revision, ExportSettings(filename='Core benchmark', folder=str(root),
                                width=1920, height=1080, fps_num=30, encoder='cpu', audio=True))
        start = time.perf_counter()
        job = service.enqueue('benchmark', root, 'final', expected_revision=revision, params={'export': payload})
        complete = await service.wait(root, job.job_id)
        assert complete.status == 'succeeded', complete.error
        report['final_export_sec'] = round(time.perf_counter() - start, 4)
        report['export_verification'] = complete.result['export_verification']
        assert report['export_verification']['passed'] and report['export_verification']['full_decode']
        probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams',
                                                  '-of', 'json', complete.result['output_path']]))
        video = next(s for s in probe['streams'] if s['codec_type'] == 'video')
        audio = next(s for s in probe['streams'] if s['codec_type'] == 'audio')
        report['output'] = {'width': video['width'], 'height': video['height'],
                            'video_sec': float(video['duration']), 'audio_sec': float(audio['duration'])}
        assert abs(float(video['duration']) - float(audio['duration'])) < 1 / 30 + .03
        report['reopen_passed'] = True
        await service.shutdown()
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(benchmark())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
