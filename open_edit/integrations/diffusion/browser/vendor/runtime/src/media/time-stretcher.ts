/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */


/**
 * Utility class for performing time stretching on a multi-channel audio signal. The input audio will be stretched by
 * a configurable factor without changing its pitch.
 *
 * Internally, this uses a WSOLA-like algorithm.
 */
export class TimeStretcher {
	factor: number; // This value can be changed at runtime

	private numberOfChannels: number;
	private synthesisHopSize: number;
	private windowSize: number;
	private overlapSize: number;
	private tolerance: number;
	private buffers: Float32Array[];
	private bufferEndIndex: number;
	private outputBuffers: Float32Array[];
	private nextOutputBufferShiftAmount: number;
	private outputBufferLength: number;
	private hasDoneOutput: boolean;
	private finalized: boolean;
	private blendValues: number[];

	public constructor(numberOfChannels: number, sampleRate: number, factor: number) {
		this.numberOfChannels = numberOfChannels;
		this.synthesisHopSize = Math.floor((512 * sampleRate) / 48000);
		this.windowSize = 2 * this.synthesisHopSize;
		this.overlapSize = this.synthesisHopSize;
		this.tolerance = this.synthesisHopSize;
		this.buffers = [];
		this.bufferEndIndex = this.tolerance;
		this.factor = factor;
		this.outputBuffers = [];
		this.nextOutputBufferShiftAmount = 0;
		this.outputBufferLength = 2 ** 16;
		this.hasDoneOutput = false;
		this.finalized = false;

		for (let i = 0; i < numberOfChannels; i++) {
			this.buffers.push(new Float32Array(2 ** 16));
			this.outputBuffers.push(new Float32Array(this.outputBufferLength));
		}

		this.blendValues = [];
		for (let i = 0; i < this.overlapSize; i++) {
			this.blendValues[i] = 0.5 * (1 - Math.cos((Math.PI * i) / this.overlapSize));
		}
	}

	private ensureOutputBufferLength(requiredLength: number): void {
		if (requiredLength > this.outputBufferLength) {
			this.outputBufferLength = requiredLength;
			for (let i = 0; i < this.numberOfChannels; i++) {
				const largerBuffer = new Float32Array(this.outputBufferLength);
				largerBuffer.set(this.outputBuffers[i], 0);
				this.outputBuffers[i] = largerBuffer;
			}
		}
	}

	private clearOutputBuffers(): void {
		if (this.nextOutputBufferShiftAmount > 0) {
			for (let i = 0; i < this.numberOfChannels; i++) {
				const buffer = this.outputBuffers[i];
				buffer.set(buffer.subarray(this.nextOutputBufferShiftAmount), 0);
			}

			this.nextOutputBufferShiftAmount = 0;
		}
	}

	private synthesizeSegment(
		i: number,
		windowSize: number,
		inputStartPos: number,
		maxPositiveOffset: number = this.tolerance
	): void {
		const crossCorrelateAllChannels = (k: number): number => {
			let dot = 0;
			let normOldTotal = 0;
			let normNewTotal = 0;

			for (let chan = 0; chan < this.numberOfChannels; chan++) {
				const inputBuffer = this.buffers[chan];
				const outputBuffer = this.outputBuffers[chan];

				for (let j = 0; j < this.overlapSize; j++) {
					const oldValue = outputBuffer[i + j];
					const newValue = inputBuffer[inputStartPos + k + j];

					dot += oldValue * newValue;
					normOldTotal += oldValue ** 2;
					normNewTotal += newValue ** 2;
				}
			}

			const ncc = dot / (Math.sqrt(normOldTotal * normNewTotal) || 1e-10);
			return ncc;
		};

		let bestCorr = -Infinity;
		let bestOffset = 0;

		if (!this.hasDoneOutput || this.factor === 1) {
			bestOffset = 0;
		} else {
			let k = -this.tolerance;
			bestCorr = crossCorrelateAllChannels(k);
			bestOffset = k;

			const minStepSize = 1;
			const maxStepSize = 16;
			let prevCorr = bestCorr;

			while (k < maxPositiveOffset) {
				const nextK = Math.min(k + 1, maxPositiveOffset);
				const corr = crossCorrelateAllChannels(nextK);

				const gradient = Math.abs(corr - prevCorr);
				const adaptiveStep = Math.max(
					minStepSize,
					Math.min(maxStepSize, Math.floor(maxStepSize * Math.exp(-gradient * 3)))
				);

				if (corr > bestCorr) {
					bestCorr = corr;
					bestOffset = nextK;
				}

				prevCorr = corr;
				k += adaptiveStep;
			}

			// Fine-tuning phase
			const fineRange = 8;
			for (k = bestOffset - fineRange; k <= bestOffset + fineRange; k++) {
				if (k >= -this.tolerance && k <= maxPositiveOffset) {
					const corr = crossCorrelateAllChannels(k);
					if (corr > bestCorr) {
						bestCorr = corr;
						bestOffset = k;
					}
				}
			}
		}

		for (let chan = 0; chan < this.numberOfChannels; chan++) {
			const inputBuffer = this.buffers[chan];
			const outputBuffer = this.outputBuffers[chan];

			for (let j = 0; j < windowSize; j++) {
				const blendValue = j < this.overlapSize ? this.blendValues[j] : 1;
				outputBuffer[i + j] *= 1 - blendValue;
				outputBuffer[i + j] += blendValue * inputBuffer[inputStartPos + bestOffset + j];
			}
		}

		this.hasDoneOutput = true;
	}

	public append(newBuffers: Float32Array[]): Float32Array[] | null {
		if (this.finalized) {
			throw new Error('Cannot append more buffers after calling finalize.');
		}

		// Fast path: when factor is 1, pass through directly without any processing
		if (this.factor === 1) {
			this.hasDoneOutput = true;
			return newBuffers;
		}

		for (let i = 0; i < this.numberOfChannels; i++) {
			const newBuffer = newBuffers[i];
			const requiredLength = this.bufferEndIndex + newBuffer.length;
			let currentLength = this.buffers[i].length;

			while (currentLength < requiredLength) {
				currentLength *= 2;
			}

			if (currentLength !== this.buffers[i].length) {
				const largerBuffer = new Float32Array(currentLength);
				largerBuffer.set(this.buffers[i], 0);
				this.buffers[i] = largerBuffer;
			}

			this.buffers[i].set(newBuffer, this.bufferEndIndex);
		}

		this.bufferEndIndex += newBuffers[0].length;

		return this.process();
	}

	private process(): Float32Array[] | null {
		let synthesisLength = 0;
		// eslint-disable-next-line no-constant-condition
		for (synthesisLength; true; synthesisLength += this.synthesisHopSize) {
			const inputShiftAmount = Math.floor(synthesisLength / this.factor);

			if (inputShiftAmount + this.windowSize + 2 * this.tolerance > this.bufferEndIndex) {
				synthesisLength -= this.synthesisHopSize;
				break;
			}
		}

		if (synthesisLength <= 0) {
			return null;
		}

		const inputShiftAmount = Math.floor(synthesisLength / this.factor);
		const outputLength = synthesisLength - this.synthesisHopSize + this.windowSize;

		this.clearOutputBuffers();
		this.ensureOutputBufferLength(outputLength);

		for (let i = 0; i < synthesisLength; i += this.synthesisHopSize) {
			const inputStartPos = this.tolerance + Math.floor(i / this.factor);
			this.synthesizeSegment(i, this.windowSize, inputStartPos);
		}

		// Shift all input buffers
		for (let chan = 0; chan < this.numberOfChannels; chan++) {
			const inputBuffer = this.buffers[chan];
			inputBuffer.set(inputBuffer.subarray(inputShiftAmount, this.bufferEndIndex), 0);
		}

		this.bufferEndIndex -= inputShiftAmount;
		this.nextOutputBufferShiftAmount = synthesisLength;

		return this.outputBuffers.map(x => x.subarray(0, synthesisLength));
	}

	public finalize(): Float32Array[] | null {
		this.finalized = true;

		// Fast path: when factor is 1, nothing is buffered
		if (this.factor === 1) {
			return null;
		}

		if (this.bufferEndIndex <= this.tolerance) {
			return null;
		}

		this.clearOutputBuffers();

		const synthesisLength = this.bufferEndIndex - this.tolerance;
		this.ensureOutputBufferLength(synthesisLength);

		this.synthesizeSegment(0, synthesisLength, this.tolerance, 0);

		return this.outputBuffers.map(x => x.subarray(0, synthesisLength));
	}
}
