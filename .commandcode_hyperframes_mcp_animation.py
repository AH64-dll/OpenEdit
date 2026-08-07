from __future__ import annotations
import asyncio,json,os,subprocess,time
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from open_edit.storage.edit_graph import EditGraphStore
P=Path('/home/ah64/Videos/video'); M='/home/ah64/apps/mlt-pipeline/.venv/bin/open-edit-mcp'; T=P/'mcp_animation.html'
E={**os.environ,'OPEN_EDIT_PREVIEW_CHUNKS':'1','OPEN_EDIT_HYPERFRAMES_BIN':'/home/ah64/apps/mlt-pipeline/node_modules/.bin/hyperframes','OPEN_EDIT_NODE_BIN':'/usr/bin/node'}
def txt(r): return '\n'.join(x.text for x in r.content if getattr(x,'type',None)=='text')
def probe(path):
 return json.loads(subprocess.run(['ffprobe','-v','error','-show_entries','format=duration,size:stream=codec_name,width,height,channels','-of','json',str(path)],capture_output=True,text=True,check=True).stdout)
async def main():
 T.write_text('''<style>html,body{margin:0;width:640px;height:360px;background:#101a35;color:white;font:32px sans-serif}.scene{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;opacity:0}.a{animation:a 2s linear both;background:#12616b}.b{animation:b 2s linear both;background:#8b3b62}@keyframes a{0%{opacity:0;transform:translateX(-40px)}20%,80%{opacity:1;transform:translateX(0)}100%{opacity:0}}@keyframes b{0%,20%{opacity:0}40%,100%{opacity:1;transform:scale(1.04)}}</style><div id="a" class="clip scene a" data-start="0" data-duration="2" data-track-index="0">HyperFrames A</div><div id="b" class="clip scene b" data-start="2" data-duration="2" data-track-index="0">HyperFrames B</div>''',encoding='utf-8')
 ids=set()
 try:
  async with stdio_client(StdioServerParameters(command=M,args=['--project',str(P)],env=E)) as (r,w):
   async with ClientSession(r,w) as s:
    await s.initialize()
    assets=json.loads(txt(await s.call_tool('query_project',{'query':'list_assets','params':{}})))['assets']
    clip=json.loads(txt(await s.call_tool('edit_project',{'operation':'add_clip','params':{'asset_hash':assets[0]['hash'],'track_id':'v1','position_sec':0,'in_point_sec':0,'out_point_sec':2}})))
    overlay=json.loads(txt(await s.call_tool('edit_project',{'operation':'add_hyperframes_overlay','params':{'template_path':T.name,'variables':{},'position_sec':0,'duration_sec':2}})))
    store=EditGraphStore(P/'.open_edit'/'edit_graph.db'); ids={op.edit_id for op in store.load_all() if op.status=='applied'}
    print('edits',clip,overlay,flush=True)
    for mode in ('proxy','final'):
     t0=time.monotonic(); result=json.loads(txt(await s.call_tool('trigger_render',{'mode':mode,'encoder':'gpu','wait':True}))); elapsed=time.monotonic()-t0
     print(mode,'elapsed_sec',round(elapsed,3),'result_ok',result.get('ok'),flush=True)
     assert result.get('ok') is True,result
     print(mode,'probe',probe(result['output_path']),flush=True)
 finally:
  T.unlink(missing_ok=True); store=EditGraphStore(P/'.open_edit'/'edit_graph.db')
  for op in store.load_all():
   if op.edit_id in ids and op.status=='applied': store.update_status(op.edit_id,'reverted',reason='animation smoke cleanup')
  print('active_ops',sum(op.status=='applied' for op in store.load_all()),flush=True)
asyncio.run(main())
