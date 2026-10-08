/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

import type { WaveformRequest, WaveformResponse } from './waveform-worker';

/**
 * Peaks a second a derived waveform holds: finer than any zoom the timeline
 * reaches, and a byte each, so an hour of audio is a few megabytes of it.
 */
export const WAVEFORM_PEAKS_PER_SECOND = 800;

/**
 * The waveform of `file`'s primary audio track, or null when it has none:
 * one byte a peak, `peaksPerSecond` of them a second, and the peak at a
 * moment of the file at that moment's index. Decoded in a worker of its own,
 * gone when it answers.
 */
export function deriveWaveform(file: Blob, peaksPerSecond = WAVEFORM_PEAKS_PER_SECOND): Promise<Uint8ClampedArray | null> {
	const worker = new Worker(new URL('./waveform-worker.ts', import.meta.url), { type: 'module' });
	return new Promise<Uint8ClampedArray | null>((resolve, reject) => {
		worker.onmessage = ({ data }: MessageEvent<WaveformResponse>) => {
			if ('error' in data) reject(new Error(data.error));
			else resolve(data.peaks);
		};
		worker.onerror = (event) => reject(new Error(event.message || 'The waveform worker failed'));
		worker.postMessage({ file, peaksPerSecond } satisfies WaveformRequest);
	}).finally(() => worker.terminate());
}

/**
 * The peaks of `data` at `target` positions: the loudest of each slice, and
 * never fewer than one position per sample.
 *
 * Asked for more positions than there are samples — a waveform zoomed in past
 * the resolution it was derived at — a position's slice is narrower than one
 * sample, and every slice whose ends round to the same sample would read
 * nothing at all: a fifth of them at the far end of the zoom, drawn as a
 * regular pattern of gaps. Holding the sample the slice starts in draws what
 * there is to draw instead; past that zoom there is no more detail to show.
 */
export function downsamplePeaks(data: Uint8ClampedArray, target: number): Uint8ClampedArray {
	const peaks = new Uint8ClampedArray(target);
	const ratio = data.length / target;

	for (let i = 0; i < target; i++) {
		const from = Math.floor(i * ratio);
		const to = Math.max(from + 1, Math.floor((i + 1) * ratio));
		let max = 0;

		for (let index = from; index < to && index < data.length; index++) {
			max = Math.max(max, data[index]!);
		}

		peaks[i] = max;
	}

	return peaks;
}
