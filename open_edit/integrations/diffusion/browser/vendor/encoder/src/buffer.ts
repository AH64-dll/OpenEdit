/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

import { BufferTarget, StreamTarget, Target } from 'mediabunny';

import type { ContainerFormat, WritableFileTarget } from './types';

export class TargetBuffer {
  public target: Target;
  public fastStart: false | 'in-memory';
  public handle: FileSystemFileHandle | WritableFileTarget | undefined;

  public constructor(
    target: StreamTarget | BufferTarget,
    fastStart: false | 'in-memory',
    handle: FileSystemFileHandle | WritableFileTarget | undefined
  ) {
    this.target = target;
    this.fastStart = fastStart;
    this.handle = handle;
  }

  public static async create(
    handle?: FileSystemFileHandle | WritableFileTarget
  ): Promise<TargetBuffer> {
    if (handle) {
      const fileStream = await handle.createWritable();
      return new TargetBuffer(new StreamTarget(fileStream, { chunked: true }), false, handle);
    }

    return new TargetBuffer(new BufferTarget(), 'in-memory', undefined);
  }

  public async close(format: ContainerFormat = 'mp4'): Promise<Blob | undefined> {
    if (this.fastStart === 'in-memory' && this.target instanceof BufferTarget) {
      if (!this.target.buffer) return;
      return new Blob([this.target.buffer], { type: mimeTypes[format] });
    }

    return undefined;
  }
}

const mimeTypes: Record<ContainerFormat, string> = {
  mp4: 'video/mp4',
  webm: 'video/webm',
  ogg: 'audio/ogg',
  mov: 'video/quicktime',
};
