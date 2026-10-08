/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

import type { StreamTargetChunk } from 'mediabunny';

/** Container format of the output file. */
export type ContainerFormat = 'mp4' | 'webm' | 'ogg' | 'mov';

// Minimal FileSystemFileHandle-shaped target
export interface WritableFileTarget {
	createWritable(): Promise<WritableStream<StreamTargetChunk>>;
}

export type EncoderProgress = {
	total: number;
	progress: number;
	remaining: Date;
};

export type ExportResult =
	| {
		type: 'success';
		data: Blob | undefined;
	}
	| {
		type: 'canceled';
	}
	| {
		type: 'error';
		error: Error;
	};
