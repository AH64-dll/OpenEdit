// MIT. Interactive host uses the exact systems and order used by image export.
import {
  createRuntimeWorld, FrameRate, RenderSurface, Mode, Library, Fonts, FramePromises,
  resetCamera, Silent, AudioEngine, Computed, Playback, Time, Host, WorldTransform,
  setActive, store, assetSystem, playbackSystem, motionSystem, transformSystem, Source, Hidden,
  renderSystem, getParentEntity,
} from '@diffusionstudio/runtime';
import { mount, getRuntimeDocument } from '@diffusionstudio/reconciler';
import { captureScene, normalizeSceneTransform, resolverSystem, warmupAssets } from './vendor/encoder/src/encoder';

let fontReady: Promise<void> | undefined;
// The source compiler deliberately removes authored `id` props. Source is the
// durable identity shared with the AST writer, rather than a runtime entity ID.
const sourceId = (entity: any) => entity?.get(Source)?.value?.split(':').at(-1);
function loadFont() {
  return fontReady ??= (async () => {
    const font = new FontFace('OpenEdit Sans', 'url(/api/studio/font.woff2)', { weight: '400' });
    await font.load(); document.fonts.add(font);
  })().catch(error => { fontReady = undefined; throw error; });
}

class Editor {
  world: any;
  mounted: any;
  scene: any;
  disposed = false;
  fps: number;
  queue: Promise<any> = Promise.resolve();
  constructor(readonly canvas: HTMLCanvasElement, readonly config: any) { this.fps = config.fps; }

  async initialize() {
    await loadFont();
    if (this.disposed) throw new Error('Editor closed');
    const world = this.world = createRuntimeWorld('openedit-interactive');
    world.set(FrameRate, { value: this.fps });
    world.set(Mode, { value: 'offline-video' });
    world.set(FramePromises, { list: [] });
    world.add(Silent);
    world.set(AudioEngine, { context: new OfflineAudioContext(2, 1, 48000) });
    resetCamera(world);
    world.set(RenderSurface, { canvas: this.canvas, ctx: this.canvas.getContext('2d'), resolution: 1 });
    world.set(Fonts, { list: [{ family: 'OpenEdit Sans', source: 'url(/api/studio/font.woff2)' }] });
    const library = new Map(this.config.assets.map((a: any) => [a.id, { ...a,
      handle: { async getFile() {
        const response = await fetch(a.url);
        if (!response.ok) throw new Error('Project image unavailable');
        return new File([await response.blob()], a.id, { type: a.mimeType });
      } },
    }]));
    world.set(Library, { get: (id: string) => library.get(id.replace('asset://', '')),
      resolve: async (id: string) => {
        const asset = library.get(id.replace('asset://', ''));
        if (!asset) throw new Error('Unknown project image');
        return asset;
      },
    });
    this.mounted = mount(this.config.code, world);
    this.scene = captureScene(world);
    await warmupAssets(world);
    if (this.disposed) throw new Error('Editor closed');
    const computed = store(world, Computed), sceneId = this.scene.id();
    this.canvas.width = computed.width[sceneId]; this.canvas.height = computed.height[sceneId];
    setActive(world, this.scene);
    const playback = store(world, Playback);
    playback.playing[sceneId] = true; playback.loop[sceneId] = false; playback.speed[sceneId] = 1;
    return this;
  }

  frame(seconds: number, props: Record<string, Record<string, unknown>> = {}, offsets: Record<string, [number, number]> = {}) {
    // Serialized seeks prevent an older asset resolution drawing over a newer frame.
    const draw = async () => {
      if (this.disposed) return [];
      const world = this.world, sceneId = this.scene.id();
      const document = getRuntimeDocument(world);
      for (const entity of world.query(Host)) {
        const node = entity.get(Host);
        for (const [key, value] of Object.entries(props[sourceId(entity)] || {})) {
          if (!['x', 'y', 'width', 'height', 'rotation', 'scale', 'scaleX', 'scaleY', 'opacity'].includes(key) ||
              typeof value !== 'number' || !Number.isFinite(value)) throw new Error('Invalid interactive property');
          document.setProperty(node, key, value);
        }
      }
      const computed = store(world, Computed), time = world.get(Time);
      const frame = Math.max(0, Math.round(seconds * this.fps));
      computed.localTimeInSeconds[sceneId] = frame / this.fps;
      computed.localTime[sceneId] = frame;
      world.set(Time, { delta: 1000 / this.fps, now: time.now + 1000 / this.fps });
      assetSystem(world); playbackSystem(world); await resolverSystem(world);
      if (this.disposed) return [];
      motionSystem(world); normalizeSceneTransform(world, sceneId);
      for (const entity of world.query(Host)) {
        const delta = offsets[sourceId(entity)];
        if (delta) {
          computed.positionX[entity.id()] += delta[0];
          computed.positionY[entity.id()] += delta[1];
        }
      }
      transformSystem(world); renderSystem(world);
      return this.geometry();
    };
    const result = this.queue.then(draw);
    this.queue = result.catch(() => {});
    return result;
  }

  geometry() {
    const world = this.world, computed = store(world, Computed);
    const result: any[] = [];
    // The authored tree order is also the paint order, including nested siblings.
    const visit = (node: any, ancestorsVisible: boolean) => {
      const entity = node.entity, id = entity?.id(), matrix = entity?.get(WorldTransform);
      const authoredId = sourceId(entity);
      const visible = ancestorsVisible && !entity?.has(Hidden) && computed.visibility[id] > 0 && computed.opacity[id] > 0;
      if (authoredId && matrix && ['rect', 'text', 'image', 'group'].includes(node.tag)) {
        const width = computed.width[id], height = computed.height[id];
        const originX = computed.originX[id] || 0, originY = computed.originY[id] || 0;
        const point = (x: number, y: number) => [matrix.a * x + matrix.c * y + matrix.e, matrix.b * x + matrix.d * y + matrix.f];
        const parent = getParentEntity(entity), parentMatrix = parent?.get(WorldTransform);
        result.push({ id: authoredId, tag: node.tag, visible, width, height,
          x: computed.positionX[id], y: computed.positionY[id], matrix, parent_matrix: parentMatrix,
          corners: [[originX, originY], [originX + width, originY], [originX + width, originY + height], [originX, originY + height]].map(([x, y]) => point(x, y)),
        });
      }
      for (const child of node.children || []) if (child.tag) visit(child, visible);
    };
    const root = this.scene.get(Host);
    if (root) visit(root, true);
    return result;
  }

  async dispose() {
    this.disposed = true;
    await this.queue.catch(() => {});
    this.mounted?.dispose(); this.world?.destroy(); this.world = undefined;
  }
}

(window as any).OpenEditCanvas = {
  async create(canvas: HTMLCanvasElement, config: any) {
    const editor = new Editor(canvas, config);
    try { return await editor.initialize(); }
    catch (error) { await editor.dispose(); throw error; }
  },
};
