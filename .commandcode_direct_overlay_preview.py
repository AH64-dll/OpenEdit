from __future__ import annotations
import asyncio,json
from pathlib import Path
from open_edit.kernel.render_jobs import RenderJobService
async def main():
 p=Path('/home/ah64/Videos/video'); s=RenderJobService(timeout_s=300)
 job=s.enqueue(p.name,p,'preview-chunks',params={'ranges':[{'start_sec':0,'end_sec':2}],'media':'video','priority':'interactive'})
 print('job',job.job_id,flush=True)
 while True:
  j=s.get(p,job.job_id); print(j.status,j.error,j.output_path,flush=True)
  if j.status in {'succeeded','failed','cancelled','orphaned'}: print(json.dumps(j.result,default=str),flush=True); break
  await asyncio.sleep(1)
asyncio.run(main())
