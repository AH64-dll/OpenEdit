
"""Minimal CDP driver for the R3 functional review (headless Chrome via websockets)."""
import asyncio, json, os, socket, subprocess, time, urllib.request

import websockets

class CDP:
    def __init__(self, ws, timeout=30):
        self.ws = ws
        self._id = 0
        self._pending = {}
        self._events = []
        self.timeout = timeout
        self._listener_task = None

    @classmethod
    async def connect(cls, url):
        ws = await websockets.connect(url, max_size=2**26, open_timeout=20)
        c = cls(ws)
        c._listener_task = asyncio.create_task(c._listen())
        return c

    async def _listen(self):
        try:
            async for raw in self.ws:
                msg = json.loads(raw)
                if 'id' in msg:
                    fut = self._pending.pop(msg['id'], None)
                    if fut and not fut.done():
                        fut.set_result(msg)
                else:
                    self._events.append(msg)
        except Exception:
            pass

    async def send(self, method, params=None):
        self._id += 1
        mid = self._id
        fut = asyncio.get_event_loop().create_future()
        self._pending[mid] = fut
        await self.ws.send(json.dumps({'id': mid, 'method': method, 'params': params or {}}))
        return await asyncio.wait_for(fut, self.timeout)

    async def call(self, method, params=None):
        resp = await self.send(method, params)
        if 'error' in resp:
            raise RuntimeError(f'{method}: {resp["error"]}')
        return resp.get('result', {})

    async def eval(self, expr, await_promise=True):
        res = await self.call('Runtime.evaluate', {
            'expression': expr,
            'returnByValue': True,
            'awaitPromise': await_promise,
        })
        if 'exceptionDetails' in res:
            raise RuntimeError('JS exception: ' + json.dumps(res['exceptionDetails'])[:500])
        return res.get('result', {}).get('value')

    async def enable_all(self):
        for m in ('Page.enable','Runtime.enable','Network.enable','Log.enable','DOM.enable'):
            try:
                await self.call(m)
            except Exception as e:
                print('enable warn', m, e)

    def drain_events(self, kind=None):
        out = []
        while self._events:
            ev = self._events.pop(0)
            if kind is None or ev.get('method') == kind:
                out.append(ev)
        return out

    async def close(self):
        try:
            await self.ws.close()
        except Exception:
            pass

    @staticmethod
    def new_page_ws(debug_port):
        # Create a fresh tab via HTTP endpoint
        with urllib.request.urlopen(f'http://127.0.0.1:{debug_port}/json/new?about:blank', timeout=10) as resp:
            info = json.loads(resp.read())
        return info['webSocketDebuggerUrl']


def launch_chrome(port=9333, user_data=None):
    user_data = user_data or f'/tmp/chrome-r3-{port}'
    subprocess.run(['pkill', '-f', f'--user-data-dir={user_data}'], capture_output=True)
    proc = subprocess.Popen([
        'google-chrome-stable', '--headless=new',
        f'--remote-debugging-port={port}',
        f'--user-data-dir={user_data}',
        '--no-first-run', '--no-default-browser-check', '--disable-gpu',
        '--window-size=1600,1000', '--hide-scrollbars', 'about:blank',
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # wait for the debugging endpoint
    for _ in range(60):
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/json/version', timeout=2) as resp:
                return proc
        except Exception:
            time.sleep(0.25)
    raise RuntimeError('chrome debug port did not come up')
