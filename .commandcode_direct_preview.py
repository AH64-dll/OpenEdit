from __future__ import annotations
import asyncio, json
from pathlib import Path
from open_edit.kernel.render_jobs import RenderJobService

async def main():
    project = Path('/home/ah64/Videos/video')
    service = RenderJobService(timeout_s=300)
    job = service.enqueue(project.name, project, 'preview-chunks', params={
        'ranges': [{'start_sec': 0.0, 'end_sec': 2.0}],
        'media': 'video', 'priority': 'interactive',
    })
    print('enqueued', job.job_id, flush=True)
    while True:
        current = service.get(project, job.job_id)
        print(json.dumps({'status': current.status, 'error': current.error, 'output': current.output_path}), flush=True)
        if current.status in {'succeeded','failed','cancelled','orphaned'}:
            print(json.dumps({'result': current.result}, default=str), flush=True)
            break
        await asyncio.sleep(1)

asyncio.run(main())
