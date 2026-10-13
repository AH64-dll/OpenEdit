#!/usr/bin/env python3
"""Verify a fresh install with actual stdio MCP edits, preview, export and reopen."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from open_edit.mcp.config import host_config
from open_edit.runtime import activate


def command(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError(f'{args[0]} failed: {result.stderr[-3000:]}')
    return result.stdout


async def verify(root: Path, graphics: bool, progress: dict) -> dict:
    def stage(name):
        progress['phase'] = name
        print(f'Verify: {name}', flush=True)

    stage('create test project and media')
    project = root / 'project with spaces'
    project.mkdir()
    command([sys.executable, '-I', '-m', 'open_edit.cli', 'init', str(project)])
    for name, color in [('one', 'red'), ('two', 'blue')]:
        command(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                 f'color=c={color}:s=320x180:r=30:d=0.8', '-c:v', 'libx264',
                 '-pix_fmt', 'yuv420p', str(root / f'{name}.mp4')])
    command(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
             'sine=frequency=440:sample_rate=48000:duration=1.6', str(root / 'score.wav')])
    config = json.loads(host_config(project))['mcpServers']['openedit']
    calls = []
    server = StdioServerParameters(command=config['command'], args=config['args'], env=dict(os.environ))
    stage('start MCP server')
    async with stdio_client(server) as (read, write), ClientSession(read, write) as session:
        stage('initialize MCP')
        initialization = await session.initialize()
        stage('list MCP tools')
        tools = await session.list_tools()
        names = sorted(tool.name for tool in tools.tools)
        assert names == sorted(['query_project', 'edit_project', 'run_script', 'trigger_render',
                                'get_render_job', 'cancel_render_job']), names
        assert len(initialization.instructions or '') < 1500
        async def call(name, args):
            detail = args.get('operation') or args.get('query') or args.get('mode') or ''
            stage(f'{name} {detail}')
            started = time.perf_counter()
            response = await session.call_tool(name, args)
            result = json.loads(response.content[0].text)
            calls.append({'tool': name, 'elapsed_sec': round(time.perf_counter() - started, 3)})
            if response.isError or result.get('status') == 'error' or result.get('ok') is False:
                raise RuntimeError(json.dumps(result))
            return result
        await call('edit_project', {'operation': 'ingest_local', 'params': {
            'paths': [str(root / name) for name in ('one.mp4', 'two.mp4', 'score.wav')]}})
        assets = (await call('query_project', {'query': 'list_assets', 'params': {}}))['assets']
        hashes = {item['filename']: item['hash'] for item in assets}
        revision = (await call('query_project', {'query': 'get_editing_context', 'params': {}}))['graph_revision']
        ops = [{'kind': 'add_clip', 'clip_id': name, 'asset_hash': hashes[name + '.mp4'],
                'track_id': 'V1', 'position_sec': i * .8, 'out_point_sec': .8}
               for i, name in enumerate(('one', 'two'))]
        ops += [{'kind': 'set_track_properties', 'track_id': 'V1', 'index': 0},
                {'kind': 'add_transition', 'clip_a_id': 'one', 'clip_b_id': 'two',
                 'transition_type': 'dissolve', 'duration_sec': .2, 'layout': 'centered'},
                {'kind': 'add_clip', 'clip_id': 'score', 'asset_hash': hashes['score.wav'],
                 'track_id': 'A1', 'track_kind': 'audio', 'position_sec': 0, 'out_point_sec': 1.6}]
        changes = []
        if graphics:
            source = '''export default function Graphics() { return <stage id="stage">
              <scene id="scene" width={320} height={180} active>
              <rect id="badge" x={20} y={20} width={60} height={32} fill="#ffd46b" end={1.6}>
                <keyframeTrack id="motion" property="x">
                  <keyframe id="start" time={0} value={20} />
                  <keyframe id="finish" time={1.6} value={230} />
                </keyframeTrack>
              </rect></scene></stage>; }'''
            changes = [{'kind': 'document', 'object_id': 'smoke-graphics', 'data': {
                'source': source, 'clip_id': 'badge', 'track_id': 'V2', 'duration_sec': 1.6, 'fps': 30}}]
        result = await call('edit_project', {'operation': 'apply_studio_changes', 'params': {
            'expected_revision': revision, 'changes': changes, 'ops': ops, 'label': 'Install smoke'}})
        saved_revision = result['graph_revision']
        preview = await call('trigger_render', {'mode': 'proxy', 'wait': True, 'encoder': 'cpu',
                             'scale': '320x180', 'quality': 'fast'})
        final = await call('trigger_render', {'mode': 'final', 'wait': True, 'encoder': 'cpu',
                           'scale': '320x180', 'quality': 'high'})
        for result in (preview, final):
            assert Path(result['output_path']).is_file()
        stage('close first MCP session')
    stage('reopen MCP project')
    async with stdio_client(server) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        response = await session.call_tool('query_project', {'query': 'get_editing_context', 'params': {}})
        assert json.loads(response.content[0].text)['graph_revision'] == saved_revision
    output = Path(final['output_path'])
    stage('check media timing, decoding and animation pixels')
    probe = json.loads(command(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(output)]))
    video = next(s for s in probe['streams'] if s['codec_type'] == 'video')
    audio = next(s for s in probe['streams'] if s['codec_type'] == 'audio')
    assert (video['width'], video['height']) == (320, 180)
    assert video['avg_frame_rate'] == '30/1'
    assert abs(float(video['duration']) - 1.6) <= 1/30
    assert abs(float(audio['duration']) - 1.6) <= 1/30
    command(['ffmpeg', '-v', 'error', '-i', str(output), '-f', 'null', '-'])
    def sample(time_, x, y):
        data = subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(time_), '-i', str(output),
                               '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                              capture_output=True, check=True, timeout=60).stdout
        return list(data[(y*320+x)*3:(y*320+x)*3+3])
    red, blend, blue = (sample(t, 300, 150) for t in (.1, .8, 1.4))
    assert red[0] > 180 and red[2] < 80, red
    assert blend[0] > 40 and blend[2] > 40, blend
    assert blue[2] > 180 and blue[0] < 80, blue
    if graphics:
        for time_, x in ((.1, 45), (1.4, 225)):
            pixel = sample(time_, x, 32)
            assert pixel[0] > 180 and pixel[1] > 140 and pixel[2] < 160, pixel
    # A wheel must also serve its bundled UI, not only expose the Python API.
    stage('start installed UI')
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    env = dict(os.environ, OPEN_EDIT_PROJECTS_ROOT=str(project.parent))
    ui = subprocess.Popen([sys.executable, '-I', '-m', 'open_edit.cli', 'serve',
                           '--host', '127.0.0.1', '--port', str(port), '--log-level', 'warning'],
                          env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for _ in range(100):
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health', timeout=1) as response:
                    assert json.loads(response.read())['status'] == 'ok'
                break
            except OSError:
                if ui.poll() is not None:
                    raise RuntimeError(ui.communicate()[1].decode(errors='replace')) from None
                await asyncio.sleep(.1)
        else:
            raise RuntimeError('Installed UI did not become ready')
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=5) as response:
            assert b'id="preview-player"' in response.read()
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/app.js', timeout=5) as response:
            assert response.status == 200 and len(response.read()) > 1000
        stage('export through installed UI API')
        def api(path, body=None):
            request = urllib.request.Request(f'http://127.0.0.1:{port}' + path,
                data=json.dumps(body).encode() if body is not None else None,
                headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read())
        projects = api('/api/projects')
        # Windows temporary paths can use 8.3 aliases; the UI returns canonical paths.
        match = next((p for p in projects if Path(p['path']).resolve() == project.resolve()), None)
        if match is None:
            raise RuntimeError(f'Test project is missing from installed UI: {projects!r}')
        project_id = match['id']
        exported = api(f'/api/projects/{project_id}/export', {
            'expected_revision': saved_revision,
            'settings': {'filename': 'Release export', 'folder': str(root / 'exports with spaces'),
                         'width': 320, 'height': 180, 'fps_num': 30, 'fps_den': 1,
                         'quality': 'high', 'encoder': 'cpu'}})
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            job = api(f"/api/projects/{project_id}/render_jobs/{exported['job_id']}")
            if job['status'] == 'succeeded':
                break
            if job['status'] in ('failed', 'cancelled', 'orphaned'):
                raise RuntimeError(json.dumps(job))
            await asyncio.sleep(.1)
        else:
            raise RuntimeError('Installed UI export did not finish')
        assert job['result']['export_verification']['passed']
        assert job['graph_revision'] == saved_revision
        output = Path(job['output_path'])
        command(['ffmpeg', '-v', 'error', '-i', str(output), '-f', 'null', '-'])
        for t, color in ((.1, 0), (1.4, 2)):
            assert sample(t, 300, 150)[color] > 180
        if graphics:
            assert sample(1.4, 225, 32)[1] > 140
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/projects/{project_id}/exports/{exported['job_id']}/file", timeout=10) as response:
            assert hashlib.sha256(response.read()).digest() == hashlib.sha256(output.read_bytes()).digest()
    finally:
        ui.terminate()
        try:
            ui.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            ui.kill()
            ui.communicate()
    return {'passed': True, 'installed_ui_verified': True, 'ui_export_verified': True,
            'tools': names, 'saved_revision': saved_revision,
            'graphics': graphics, 'duration_sec': float(video['duration']),
            'preview_verified': True, 'export_verified': True, 'reopen_verified': True, 'cut_transition_pixels_verified': True,
            'animated_overlay_pixels_verified': graphics,
            'sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'calls': calls,
            'output_path': str(output)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--graphics', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    activate()
    started = time.perf_counter()
    progress = {'phase': 'start'}
    with tempfile.TemporaryDirectory(prefix='openedit-install-check-') as scratch:
        # This fixed 1.6-second workflow must fail promptly if a worker stalls.
        async def bounded_verify():
            return await asyncio.wait_for(verify(Path(scratch), args.graphics, progress), timeout=300)
        try:
            report = asyncio.run(bounded_verify())
        except Exception as error:
            report = {'passed': False, **progress, 'error': repr(error),
                      'elapsed_sec': round(time.perf_counter() - started, 3)}
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
            raise RuntimeError(f"Installation verification failed during {progress['phase']}: {error!r}") from error
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            artifact = args.output.with_suffix('.mp4')
            shutil.copy2(report['output_path'], artifact)
            report['output_path'] = str(artifact.resolve())
            report['elapsed_sec'] = round(time.perf_counter() - started, 3)
            args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
