/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

import { generate, transform } from '@diffusionstudio/jsx';

import type { Entity, World } from 'koota';
import type { Asset } from '@diffusionstudio/assets';
import type {
	AssetInput,
	AssetRef,
	GenerateAudioOptions,
	GenerateImageOptions,
	GenerateVideoOptions,
	GenerateVoiceOptions,
} from '@diffusionstudio/jsx';

/**
 * The generation service a host attaches to its world. Where a generation
 * stands is the library's to hold, as partial documents (see
 * `PartialAsset` in @diffusionstudio/assets): a run that starts is
 * `pending` there, one that lands is the asset, one that fails stays as
 * `error` with its reason — and a key standing in error resolves to that
 * error rather than to another run, in this session and the next. Nothing
 * here writes to the source that declared the generation.
 */
export abstract class GenAi {
	/**
	 * The declaration, made real: an asset whose bytes the model produced —
	 * from a prompt (`generate.*`) or from another asset (`transform.*`), its
	 * inputs resolved first. Content-addressed — the fully-resolved spec's
	 * hash is the asset's `generation.key`, so the same spec is the same
	 * asset in this session and the next, and identical concurrent
	 * declarations share one run. Rejects with the recorded reason when the
	 * key stands in error.
	 */
	public abstract resolve(ref: AssetRef): Promise<Asset>;

	/**
	 * The transcript of `scene`'s audible mix, as a TRANSCRIPT asset of the
	 * project's library. Cached by scene id + seed: the same pair resolves to
	 * the same asset, in this session and the next, and a new seed transcribes
	 * the scene again. Identical concurrent requests share one run.
	 */
	public abstract transcribe(world: World, scene: Entity, seed: number): Promise<Asset>;

	/**
	 * The imperative surface: `ai.generate.image({...})` declares and resolves
	 * in one call, returning the finished asset.
	 */
	public readonly generate = {
		image: (options: GenerateImageOptions): Promise<Asset> => this.resolve(generate.image(options)),
		video: (options: GenerateVideoOptions): Promise<Asset> => this.resolve(generate.video(options)),
		voice: (options: GenerateVoiceOptions): Promise<Asset> => this.resolve(generate.voice(options)),
		audio: (options: GenerateAudioOptions): Promise<Asset> => this.resolve(generate.audio(options)),
	};

	/** The same for `transform.*`: `ai.transform.upscale(input)` is the upscaled asset. */
	public readonly transform = {
		upscale: (input: AssetInput): Promise<Asset> => this.resolve(transform.upscale(input)),
		removeBackground: (input: AssetInput): Promise<Asset> => this.resolve(transform.removeBackground(input)),
		addAudio: (input: AssetInput): Promise<Asset> => this.resolve(transform.addAudio(input)),
	};
}
