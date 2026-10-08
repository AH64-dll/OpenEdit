// MIT host over the pinned, unchanged MPL runtime, reconciler, and encoder.
import { createRuntimeWorld, FrameRate, RenderSurface, Mode, Library, Fonts } from '@diffusionstudio/runtime';
import { mount } from '@diffusionstudio/reconciler';
import { createImageEncoder } from '@diffusionstudio/encoder';

let world: any;
let mounted: any;
(window as any).openEdit = {
  async mount(code: string, fps: number, assets: any[]) {
    world = createRuntimeWorld('openedit-capture');
    world.set(FrameRate, { value: fps });
    world.set(Mode, { value: 'offline-video' });
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
    const result = await encoder.render();
    if (result.type !== 'success') throw new Error(result.type === 'error' ? result.error.message : 'Capture cancelled');
    // Bounded to one frame per host round trip; no movie-sized JS/base64 buffer.
    const bytes = result.data[0].png; let binary = '';
    for (let i = 0; i < bytes.length; i += 32768) binary += String.fromCharCode(...bytes.subarray(i, i + 32768));
    return btoa(binary);
  },
  dispose() { mounted?.dispose(); world?.destroy(); document.body.replaceChildren(); },
};
