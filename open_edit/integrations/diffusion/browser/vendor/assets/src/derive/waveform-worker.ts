/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

// The waveform of a media file, computed off the main thread: the peak
// amplitude of each slice of its audio (across channels, gamma-lifted so
// quiet passages still show), as a byte. WebCodecs decodes elsewhere already,
// but PCM formats (WAV) are unpacked in JS and would stall the UI. One worker
// per request: a file and a resolution in, the whole waveform out.

import { ALL_FORMATS, AudioSampleSink, BlobSource, Input } from 'mediabunny';

export interface WaveformRequest {
	file: Blob;
	peaksPerSecond: number;
}

export type WaveformResponse = { peaks: Uint8ClampedArray | null } | { error: string };

// The package is typed against the DOM lib, so the worker scope is narrowed by hand.
const scope = self as unknown as {
	onmessage: ((event: MessageEvent<WaveformRequest>) => void) | null;
	postMessage(message: WaveformResponse, transfer?: Transferable[]): void;
};

scope.onmessage = async ({ data: { file, peaksPerSecond } }) => {
	try {
		const peaks = await computeWaveform(file, peaksPerSecond);
		scope.postMessage({ peaks }, peaks ? [peaks.buffer as ArrayBuffer] : []);
	} catch (error) {
		scope.postMessage({ error: error instanceof Error ? error.message : String(error) });
	}
};

/**
 * The waveform of `file`'s primary audio track, or null when it has none.
 *
 * Every peak is written where it belongs rather than appended, so a track
 * that starts at a timestamp of its own or has a gap in it still lines up
 * with the time it is drawn against.
 */
async function computeWaveform(file: Blob, peaksPerSecond: number): Promise<Uint8ClampedArray | null> {
	const input = new Input({ formats: ALL_FORMATS, source: new BlobSource(file) });
	try {
		const track = await input.getPrimaryAudioTrack();
		if (!track) return null;

		// The track's own end, so a file whose sound outlasts its picture (or
		// starts after it) is as long here as it is on disk.
		const peaks = new Uint8ClampedArray(Math.ceil((await track.computeDuration()) * peaksPerSecond));
		const sink = new AudioSampleSink(track);
		let covered = 0;

		for await (const sample of sink.samples()) {
			let floats: Float32Array;
			let channels: number;
			let timestamp: number;
			let duration: number;

			// Everything the sample holds is taken before it is closed, and it
			// is closed however that goes: they are decoder resources.
			try {
				const size = sample.allocationSize({ format: 'f32', planeIndex: 0 });
				floats = new Float32Array(size / Float32Array.BYTES_PER_ELEMENT);
				sample.copyTo(floats, { format: 'f32', planeIndex: 0 });
				channels = sample.numberOfChannels;
				timestamp = sample.timestamp;
				duration = sample.duration;
			} finally {
				sample.close();
			}

			const frames = floats.length / channels;
			const from = Math.floor(timestamp * peaksPerSecond);
			const to = Math.min(peaks.length, from + Math.ceil(duration * peaksPerSecond));
			const ratio = frames / Math.max(1, to - from);

			for (let peak = from; peak < to; peak++) {
				const start = Math.floor((peak - from) * ratio);
				const end = Math.floor((peak - from + 1) * ratio);
				let max = 0;

				for (let frame = start; frame < end && frame < frames; frame++) {
					for (let channel = 0; channel < channels; channel++) {
						max = Math.max(max, Math.pow(Math.abs(floats[frame * channels + channel]!), 0.8));
					}
				}

				peaks[peak] = Math.floor(255 * max);
			}

			covered = Math.max(covered, to);
		}

		if (covered === 0) return null;

		return covered === peaks.length ? peaks : peaks.slice(0, covered);
	} finally {
		input.dispose();
	}
}
