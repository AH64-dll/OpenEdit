from __future__ import annotations
import json, os, subprocess, time
env={**os.environ,'OPEN_EDIT_HYPERFRAMES_BIN':'/home/ah64/apps/mlt-pipeline/node_modules/.bin/hyperframes','OPEN_EDIT_NODE_BIN':'/usr/bin/node','OPEN_EDIT_FORCE_CLEAN_CACHE':''}
subprocess.run(['mv','/home/ah64/Videos/video/.open_edit/renders/project_fe5214616f5a.mp4','/home/ah64/Videos/video/.open_edit/renders/_proxy_keep.mp4'] if os.path.exists('/home/ah64/Videos/video/.open_edit/renders/project_fe5214616f5a.mp4') else ['true'],check=False)
subprocess.run(['mv','/home/ah64/Videos/video/.open_edit/renders/project_fe5214616f5a.audio.wav','/home/ah64/Videos/video/.open_edit/renders/_audio_keep.wav'] if os.path.exists('/home/ah64/Videos/video/.open_edit/renders/project_fe5214616f5a.audio.wav') else ['true'],check=False)
subprocess.run(['rm','-rf','/home/ah64/Videos/video/.open_edit/render_cache'],check=False)
