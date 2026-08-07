from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PROJECT = Path('/home/ah64/Videos/video')
MCP = Path('/home/ah64/apps/mlt-pipeline/.venv/bin/open-edit-mcp')
ENV = {
    **os.environ,
    'OPEN_EDIT_PREVIEW_CHUNKS': '1',
    'OPEN_EDIT_HYPERFRAMES_BIN': '/home/ah64/apps/mlt-pipeline/node_modules/.bin/hyperframes',
    'OPEN_EDIT_NODE_BIN': '/usr/bin/node',
    'OPEN_EDIT_INGEST_ALLOWLIST': '/home/ah64/Videos:/home/ah64/apps/mlt-pipeline',
}


def text(result):
    return '\n'.join(item.text for item in result.content if getattr(item, 'type', None) == 'text')


async def main():
    params = StdioServerParameters(command=str(MCP), args=['--project', str(PROJECT)], env=ENV)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            edit = await session.call_tool('edit_project', {
                'operation': 'add_hyperframes_overlay',
                'params': {
                    'template_path': 'templates/mcp_smoke_title.html',
                    'variables': {'title': 'MCP HyperFrames Smoke'},
                    'position_sec': 0.0,
                    'duration_sec': 2.0,
                },
            })
            edit_data = json.loads(text(edit))
            print(json.dumps({'edit': edit_data}, sort_keys=True))
            assert edit_data.get('status') == 'ok', edit_data

            render = await session.call_tool('trigger_render', {
                'mode': 'proxy',
                'encoder': 'gpu',
                'quality': 'fast',
                'wait': False,
            })
            render_data = json.loads(text(render))
            print(json.dumps({'render_enqueue': render_data}, sort_keys=True))
            assert render_data.get('ok') and render_data.get('job_id'), render_data
            job_id = render_data['job_id']
            terminal = None
            for _ in range(900):
                job = await session.call_tool('get_render_job', {'job_id': job_id})
                data = json.loads(text(job))
                if data.get('status') != 'running':
                    print(json.dumps({'job': {
                        'job_id': data.get('job_id'),
                        'status': data.get('status'),
                        'error': data.get('error'),
                        'result': data.get('result'),
                    }}, sort_keys=True))
                if data.get('status') in {'succeeded', 'failed', 'cancelled', 'orphaned'}:
                    terminal = data
                    break
                await asyncio.sleep(1)
            assert terminal and terminal.get('status') == 'succeeded', terminal
            result = terminal.get('result') or {}
            output = Path(result.get('output_path', ''))
            assert output.is_file() and output.stat().st_size > 0, result
            print(json.dumps({'output_path': str(output), 'bytes': output.stat().st_size}, sort_keys=True))


if __name__ == '__main__':
    asyncio.run(main())
