/**
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 */

import { EncodedPacketSink } from 'mediabunny';

import type { InputVideoTrack } from 'mediabunny';

/**
 * Key packets walked between two yields to the event loop. Keeps an all-intra
 * track (every packet is a keyframe) from starving the render loop.
 */
const YIELD_INTERVAL = 512;

const indexCache = new Map<string, KeyframeIndex>();

export function clearKeyframeIndexCache() {
	indexCache.clear();
}

/**
 * Returns the shared keyframe index for an asset, starting the walk on first
 * access. Cheap to call repeatedly — one index is built per asset, not per decoder.
 */
export function getKeyframeIndex(assetId: string, track: InputVideoTrack): KeyframeIndex {
	let index = indexCache.get(assetId);

	if (!index) {
		index = new KeyframeIndex(track);
		indexCache.set(assetId, index);
	}

	return index;
}

/**
 * Ascending presentation timestamps of every key packet in a video track, walked
 * ahead of time so seeking resolves its seed keyframe with a binary search
 * instead of a container lookup.
 */
export class KeyframeIndex {
	private timestamps: number[] = [];
	private complete = false;

	public constructor(track: InputVideoTrack) {
		this.build(track);
	}

	private async build(track: InputVideoTrack) {
		try {
			const sink = new EncodedPacketSink(track);

			let packet = await sink.getFirstKeyPacket({ metadataOnly: true });
			let walked = 0;

			while (packet) {
				this.timestamps.push(packet.timestamp);

				// `getNextKeyPacket` resolves without I/O once the sample table is parsed,
				// so awaiting it only queues a microtask and never lets the browser paint.
				// A timer is a macrotask, which does.
				if (++walked % YIELD_INTERVAL === 0) {
					await new Promise((resolve) => setTimeout(resolve));
				}

				packet = await sink.getNextKeyPacket(packet, { metadataOnly: true });
			}

			this.complete = true;
		} catch (e) {
			// A disposed input (project closed, permission revoked) lands here; the
			// index simply stays incomplete and callers fall back to a container lookup.
			console.error('Error building keyframe index', e);
		}
	}

	/**
	 * Timestamp of the last keyframe at or before `seconds`, or `null` when the
	 * index cannot answer: `seconds` precedes the first keyframe, or the walk has
	 * not reached that far yet and a closer keyframe may still show up.
	 */
	public floor(seconds: number): number | null {
		const timestamps = this.timestamps;
		const length = timestamps.length;

		if (length === 0 || seconds < timestamps[0]) {
			return null;
		}
		if (!this.complete && seconds > timestamps[length - 1]) {
			return null;
		}

		let low = 0;
		let high = length - 1;

		while (low < high) {
			const mid = (low + high + 1) >> 1;
			if (timestamps[mid] <= seconds) {
				low = mid;
			} else {
				high = mid - 1;
			}
		}

		return timestamps[low];
	}
}
