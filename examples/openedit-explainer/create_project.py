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
        await call('edit_project', {'operation': 'ingest_local', 'params': {'paths': [
            str(source / 'music.wav'), str(source / 'sound-effects.wav')]}})
        assets = await call('query_project', {'query': 'list_assets', 'params': {}})
        audio = {asset['filename']: asset['hash'] for asset in assets['assets']}
        context = await call('query_project', {'query': 'get_editing_context', 'params': {}})
        result = await call('edit_project', {'operation': 'apply_studio_changes', 'params': {
            'expected_revision': context['graph_revision'], 'label': 'Create OpenEdit kinetic trailer',
            'changes': [{'kind': 'document', 'object_id': 'openedit-explainer', 'data': {
                'source': (source / 'scene.jsx').read_text(encoding='utf-8'), 'clip_id': 'explainer',
                'track_id': 'V1', 'duration_sec': 10, 'fps': 60, 'label': 'OpenEdit — Put your ideas in motion.'}}],
            'ops': [{'kind': 'add_clip', 'clip_id': 'music', 'asset_hash': audio['music.wav'],
                     'track_id': 'A1', 'track_kind': 'audio', 'position_sec': 0, 'out_point_sec': 10},
                    {'kind': 'add_clip', 'clip_id': 'sound-effects', 'asset_hash': audio['sound-effects.wav'],
                     'track_id': 'A2', 'track_kind': 'audio', 'position_sec': 0, 'out_point_sec': 10}]}})
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    asyncio.run(create(parser.parse_args().project.expanduser().resolve()))
