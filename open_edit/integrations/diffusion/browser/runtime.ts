// MIT host over the pinned, unchanged MPL runtime, reconciler, and encoder.
import { createRuntimeWorld, FrameRate, RenderSurface, Mode, Library, Fonts, FramePromises, resetCamera, Time, Computed, store, assetSystem, playbackSystem, motionSystem } from '@diffusionstudio/runtime';
import { mount } from '@diffusionstudio/reconciler';
import { createImageEncoder } from '@diffusionstudio/encoder';
import { captureScene, normalizeSceneTransform, resolverSystem } from './vendor/encoder/src/encoder';
import { settleGeometry } from './settle-geometry';

let world: any;
let mounted: any;
(window as any).openEdit = {
  async mount(code: string, fps: number, assets: any[]) {
    world = createRuntimeWorld('openedit-capture');
    world.set(FrameRate, { value: fps });
    world.set(Mode, { value: 'offline-video' });
    world.set(FramePromises, { list: [] });
    // The Camera trait's interactive-editor default (30% zoom, panned) is not a
    // capture view: without an identity reset every frame renders off-canvas.
    resetCamera(world);
    const canvas = document.createElement('canvas'); document.body.append(canvas);
    world.set(RenderSurface, { canvas, ctx: canvas.getContext('2d'), resolution: 1 });
    const font = new FontFace('OpenEdit Sans', 'url(https://openedit.invalid/font.woff2)', { weight: '400' });
    await font.load(); document.fonts.add(font);
    world.set(Fonts, { list: [{ family: 'OpenEdit Sans', source: 'url(https://openedit.invalid/font.woff2)' }] });
    const library = new Map(assets.map(a => [a.id, { ...a,
      handle: { async getFile() { return new File([await (await fetch(a.url)).blob()], a.id, { type: a.mimeType }); } },
    }]));
    world.set(Library, { get: (id: string) => library.get(id.replace('asset://', '')),
      resolve: async (id: string) => { const a = library.get(id.replace('asset://', '')); if (!a) throw new Error('Unknown CAS asset'); return a; },
    });
    mounted = mount(code, world);
  },
  async frame(index: number) {
    const encoder = await createImageEncoder(world, { frames: [index] });
    // Resolve nested group bounds for this exact frame before the encoder's
    // unchanged systems pass, so first-frame export and interactive seek agree.
    const scene=captureScene(world), computed=store(world,Computed), fps=world.get(FrameRate).value;
    computed.localTime[scene.id()]=index; computed.localTimeInSeconds[scene.id()]=index/fps;
    const time=world.get(Time);world.set(Time,{delta:1000/fps,now:time.now+1000/fps});
    assetSystem(world);playbackSystem(world);await resolverSystem(world);motionSystem(world);
    normalizeSceneTransform(world,scene.id());settleGeometry(world,scene);
    const result = await encoder.render();
    if (result.type !== 'success') throw new Error(result.type === 'error' ? result.error.message : 'Capture cancelled');
    // Bounded to one frame per host round trip; no movie-sized JS/base64 buffer.
    const bytes = result.data[0].png; let binary = '';
    for (let i = 0; i < bytes.length; i += 32768) binary += String.fromCharCode(...bytes.subarray(i, i + 32768));
    return btoa(binary);
  },
  dispose() { mounted?.dispose(); world?.destroy(); document.body.replaceChildren(); },
};
