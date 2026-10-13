"""Create the explainer through OpenEdit's stdio editing interface."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def create(project: Path) -> None:
    if (project / '.open_edit').exists():
        raise RuntimeError('Choose a new project folder; existing projects are preserved.')
    project.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, '-I', '-m', 'open_edit.cli', 'init', str(project)], check=True)
    server = StdioServerParameters(command=sys.executable,
                                  args=['-I', '-m', 'open_edit.mcp.server', '--project', str(project)],
                                  env=dict(os.environ))
    async with stdio_client(server) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        async def call(name, args):
            response = await session.call_tool(name, args)
            result = json.loads(response.content[0].text)
            if response.isError or result.get('status') == 'error':
                raise RuntimeError(result)
            return result
        source = Path(__file__).resolve().parent
        await call('edit_project', {'operation': 'ingest_local', 'params': {'paths': [str(source / 'score.wav')]}})
        assets = await call('query_project', {'query': 'list_assets', 'params': {}})
        score = next(asset['hash'] for asset in assets['assets'] if asset['filename'] == 'score.wav')
        context = await call('query_project', {'query': 'get_editing_context', 'params': {}})
        result = await call('edit_project', {'operation': 'apply_studio_changes', 'params': {
            'expected_revision': context['graph_revision'], 'label': 'Create OpenEdit explainer',
            'changes': [{'kind': 'document', 'object_id': 'openedit-explainer', 'data': {
                'source': (source / 'scene.jsx').read_text(encoding='utf-8'), 'clip_id': 'explainer',
                'track_id': 'V1', 'duration_sec': 10, 'fps': 30, 'label': 'OpenEdit — Think it. Edit it.'}}],
            'ops': [{'kind': 'add_clip', 'clip_id': 'score', 'asset_hash': score, 'track_id': 'A1',
                     'track_kind': 'audio', 'position_sec': 0, 'out_point_sec': 10},
                    {'kind': 'set_audio_gain', 'clip_id': 'score', 'gain_db': 9.5}]}})
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    asyncio.run(create(parser.parse_args().project.expanduser().resolve()))
