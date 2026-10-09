/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

import type { TargetBuffer } from './buffer';
import type { ContainerFormat } from './types';

/**
 * Lazily imports the output format based on the format specified
 */
export async function createOutputFormat(buffer: TargetBuffer, format?: ContainerFormat) {
  if (format == 'webm') {
    const { WebMOutputFormat } = await import('mediabunny');
    return new WebMOutputFormat();
  } else if (format == 'ogg') {
    const { OggOutputFormat } = await import('mediabunny');
    return new OggOutputFormat();
  } else if (format == 'mov') {
    const { MovOutputFormat } = await import('mediabunny');
    return new MovOutputFormat();
  } else {
    const { Mp4OutputFormat } = await import('mediabunny');
    return new Mp4OutputFormat({ fastStart: buffer.fastStart });
  }
}
