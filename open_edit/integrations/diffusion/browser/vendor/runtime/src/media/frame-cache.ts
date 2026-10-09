/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

type FrameCacheConfig = {
  pixels: number;
  count: number;
}

type FrameTile = {
  tileIndex: number;
  frameIndex: number;
}

type Frame = VideoFrame | ImageBitmap;

function getDisplaySize(frame: Frame) {
  if (frame instanceof VideoFrame) {
    return [frame.displayWidth, frame.displayHeight];
  }
  return [frame.width, frame.height]
}

export class FrameCache {
  public readonly config: FrameCacheConfig;
  public readonly atlas = new OffscreenCanvas(0, 0);
  public readonly atlasCtx = this.atlas.getContext('2d')!;
  public readonly source = new OffscreenCanvas(0, 0);
  public readonly sourceCtx = this.source.getContext('2d')!;

  private tileWidth: number = 0;
  private tileHeight: number = 0;
  private columns: number = 0;
  private tiles: FrameTile[];

  public rotation: number = 0;
  public leftFrameIndex: number;
  public rightFrameIndex: number;
  public lastInserted: number = -1;

  public constructor(config: FrameCacheConfig) {
    this.config = config;
    this.leftFrameIndex = 0;
    this.rightFrameIndex = config.count - 1;
    this.tiles = [];
  }

  private resizeCaches(frame: Frame) {
    const rotation = this.rotation;
    const [width, height] = getDisplaySize(frame);
    const pixelCount = width * height;

    const factor = Math.min(1, Math.sqrt(this.config.pixels / pixelCount));

    const sourceWidth = rotation === 90 || rotation === 270
      ? height
      : width;

    const sourceHeight = rotation === 90 || rotation === 270
      ? width
      : height;

    this.tileWidth = Math.floor(sourceWidth * factor);
    this.tileHeight = Math.floor(sourceHeight * factor);

    // Lay tiles in a 2D grid
    this.columns = Math.ceil(Math.sqrt(this.config.count));
    const rows = Math.ceil(this.config.count / this.columns);

    const absoluteWidth = this.tileWidth * this.columns;
    const absoluteHeight = this.tileHeight * rows;

    if (this.atlas.width !== absoluteWidth || this.atlas.height !== absoluteHeight) {
      this.atlas.width = absoluteWidth;
      this.atlas.height = absoluteHeight;
      this.atlasCtx.imageSmoothingQuality = 'high';
      this.tiles = []; // setting the canvas size resets the tiles
    }
  }

  private drawRotated(frame: Frame) {
    const ctx = this.sourceCtx;
    const rotation = this.rotation;

    const [displayWidth, displayHeight] = getDisplaySize(frame);

    const width = rotation === 90 || rotation === 270
      ? displayHeight
      : displayWidth;

    const height = rotation === 90 || rotation === 270
      ? displayWidth
      : displayHeight;

    if (this.source.width !== width || this.source.height !== height) {
      this.source.width = width;
      this.source.height = height;
      ctx.imageSmoothingEnabled = false;
    }

    ctx.resetTransform();
    ctx.clearRect(0, 0, width, height);
    ctx.translate(width / 2, height / 2);
    ctx.rotate((rotation * Math.PI) / 180);
    ctx.drawImage(frame, -displayWidth / 2, -displayHeight / 2, displayWidth, displayHeight);
  }

  private evictTiles() {
    if (this.tiles.length < this.config.count) return;

    this.tiles = this.tiles.filter(t => t.frameIndex >= this.leftFrameIndex && t.frameIndex <= this.rightFrameIndex);
  }

  private insertTile(frameIndex: number) {
    let tileIndex = 0;
    while (this.tiles.some(t => t.tileIndex === tileIndex)) {
      tileIndex++;
    }

    this.tiles.push({ tileIndex, frameIndex });

    const ctx = this.atlasCtx;
    const x = (tileIndex % this.columns) * this.tileWidth;
    const y = Math.floor(tileIndex / this.columns) * this.tileHeight;

    ctx.clearRect(x, y, this.tileWidth, this.tileHeight);
    ctx.drawImage(this.source, x, y, this.tileWidth, this.tileHeight);
  }

  public has(frameIndex: number) {
    return this.tiles.some(t => t.frameIndex === frameIndex);
  }

  /**
   * Frame index of the cached frame closest to `frameIndex`, or `undefined` when
   * nothing is cached within `tolerance`. Ties resolve to the earlier frame, so a
   * playhead sitting between two cached frames never shows one that hasn't played yet.
   */
  public findNearest(frameIndex: number, tolerance: number): number | undefined {
    let best: number | undefined;
    let bestDistance = tolerance + 1;

    for (const tile of this.tiles) {
      const distance = Math.abs(tile.frameIndex - frameIndex);
      if (distance < bestDistance || (best !== undefined && distance === bestDistance && tile.frameIndex < best)) {
        bestDistance = distance;
        best = tile.frameIndex;
      }
    }

    return best;
  }

  public insert(frame: VideoFrame | ImageBitmap, index: number) {
    if (this.has(index)) return;

    this.evictTiles();
    this.resizeCaches(frame);
    this.drawRotated(frame);
    this.insertTile(index);
    this.lastInserted = index;
  }

  public findTile(frameIndex: number) {
    const tile = this.tiles.find(t => t.frameIndex === frameIndex);

    if (!tile) return;

    const x = (tile.tileIndex % this.columns) * this.tileWidth;
    const y = Math.floor(tile.tileIndex / this.columns) * this.tileHeight;

    return { x, y, width: this.tileWidth, height: this.tileHeight };
  }

  public dispose() {
    this.atlas.width = 0;
    this.atlas.height = 0;
    this.source.width = 0;
    this.source.height = 0;
    this.tileWidth = 0;
    this.tileHeight = 0;
    this.columns = 0;
    this.lastInserted = -1;
    this.tiles = [];
  }
}
