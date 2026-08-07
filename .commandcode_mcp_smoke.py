from __future__ import annotations

import asyncio
import json
import os
import sys
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
    parts = []
    for item in result.content:
        if getattr(item, 'type', None) == 'text':
            parts.append(item.text)
    return '\n'.join(parts)


async def main():
    params = StdioServerParameters(
        command=str(MCP),
        args=['--project', str(PROJECT)],
        env=ENV,
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            tools = await session.list_tools()
            resources = await session.list_resources()
            prompts = await session.list_prompts()
            print(json.dumps({
                'server': init.serverInfo.model_dump() if init.serverInfo else None,
                'tools': [tool.name for tool in tools.tools],
                'resources': [str(resource.uri) for resource in resources.resources],
                'prompts': [prompt.name for prompt in prompts.prompts],
            }, sort_keys=True))

            query = await session.call_tool('query_project', {
                'query': 'list_assets',
                'params': {'detail': True, 'include_derivatives': False},
            })
            print(json.dumps({'query_project': json.loads(text(query))}, sort_keys=True))

            preview = await session.call_tool('trigger_render', {
                'mode': 'preview-chunks',
                'ranges': [{'start_sec': 0.0, 'end_sec': 2.0}],
                'media': 'both',
                'priority': 'interactive',
                'wait': False,
            })
            preview_data = json.loads(text(preview))
            print(json.dumps({'preview_enqueue': preview_data}, sort_keys=True))
            job_id = preview_data.get('job_id')
            if job_id:
                for _ in range(180):
                    job = await session.call_tool('get_render_job', {'job_id': job_id})
                    data = json.loads(text(job))
                    print(json.dumps({'job': {
                        'job_id': data.get('job_id'),
                        'status': data.get('status'),
                        'mode': data.get('mode'),
                        'error': data.get('error'),
                    }}, sort_keys=True))
                    if data.get('status') in {'succeeded', 'failed', 'cancelled', 'orphaned'}:
                        break
                    await asyncio.sleep(1)


if __name__ == '__main__':
    asyncio.run(main())
