/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

// Playhead control. Where the playhead is and whether it is moving are not
// part of the composition — nothing rendered or exported depends on them —
// so these write the traits themselves and nothing reaches the file, the
// same reason the canvas toggles Playback rather than going through an
// editor. `playbackSystem` advances the playhead from here while playing.

import { store } from '../world/store';
import {
	Audio, AudioEngine, Cache, Computed, FrameRate, Geometry, Paint,
	Playback, Scene, Stage, Workarea,
} from '../traits';
import { PaintType } from '../constants';
import { getIntrinsicPaint } from '../utils/time';
import { getParentEntity } from '../queries/hierarchy';

import type { Entity, World } from 'koota';

/**
 * Whether a node plays media of its own: audio, or video through its
 * intrinsic paint or one of its fills.
 */
function hasPlayableMedia(entity: Entity): boolean {
	if (entity.has(Audio) || getIntrinsicPaint(entity) === PaintType.VIDEO) return true;

	for (const fill of entity.get(Cache)?.fills ?? []) {
		if (fill.get(Paint)?.value === PaintType.VIDEO) return true;
	}

	return false;
}

/**
 * Keeps Playback in step with where `entity` sits: a video or audio directly
 * on the stage plays like a scene — the playhead its header's play toggle
 * drives is its own — while nested under a scene it derives its time from it.
 * The hierarchy observers call this after every attach and detach, for both
 * the node itself and the parent a media fill just made (or stopped making)
 * playable, once the caches it reads are rebuilt. Scenes own their Playback
 * from creation and are left alone, as is anything without a geometry (the
 * encoder's synthetic clock is a bare group).
 */
export function syncStagePlayback(entity: Entity): void {
	if (!entity.has(Geometry) || entity.has(Scene)) return;

	if (getParentEntity(entity)?.has(Stage) && hasPlayableMedia(entity)) {
		if (!entity.has(Playback)) entity.add(Playback);
	} else if (entity.has(Playback)) {
		entity.remove(Playback);
	}
}

/**
 * Moves `scene`'s playhead to `frame` — a seek, which is what a scrub of the
 * ruler or a click in the timeline comes to. Both mirrors of the playhead are
 * written: the seconds are what audio is scheduled against and what the next
 * advance carries on from, the frames what everything comparing nodes works
 * in. Frames before the start of the scene do not exist; past its end they
 * do, since a scene is as long as what is in it and dropping a clip out there
 * is how it gets longer.
 */
export function setPlayhead(world: World, scene: Entity, frame: number): void {
	const computed = store(world, Computed);
	const fps = world.get(FrameRate)?.value ?? 30;
	const eid = scene.id();

	const clamped = Math.max(0, Math.round(frame));

	computed.localTime[eid] = clamped;
	computed.localTimeInSeconds[eid] = clamped / fps;
}

/**
 * Moves the playhead off the end it is parked against, in the direction play
 * is about to take: parked there it would stop on the first advance, so a
 * finished scene plays again from the top of its window and one sitting at
 * the top runs backwards from its end.
 */
function rewindIfParked(world: World, scene: Entity, direction: 1 | -1): void {
	const computed = store(world, Computed);
	const eid = scene.id();
	const workarea = scene.has(Workarea) ? scene.get(Workarea) : undefined;
	const start = workarea?.start ?? 0;
	const end = workarea?.end ?? computed.duration[eid] ?? 0;
	if (end <= 0) return;

	const frame = computed.localTime[eid] ?? 0;

	if (direction === 1 && frame >= end) setPlayhead(world, scene, start);
	if (direction === -1 && frame <= start) setPlayhead(world, scene, end);
}

/**
 * The audio context is gated until it has seen a gesture, and starting
 * playback is one, so it is resumed wherever play begins rather than at every
 * call site that can start it.
 */
function resumeAudioContext(world: World): void {
	const context = world.get(AudioEngine)?.context;
	if (context instanceof AudioContext) void context.resume();
}

/** Starts or stops `scene` at 1x — what the play toggle and space do. */
export function togglePlayback(world: World, scene: Entity): void {
	const playback = scene.get(Playback);
	if (!playback) return;

	if (!playback.playing) rewindIfParked(world, scene, 1);

	scene.set(Playback, { playing: !playback.playing, speed: 1 });
	resumeAudioContext(world);
}

/** Stops `scene` wherever it is, at whatever speed it was going — K. */
export function stopPlayback(_world: World, scene: Entity): void {
	if (!scene.has(Playback)) return;

	scene.set(Playback, { playing: false, speed: 1 });
}

/** The rungs J and L climb, as multiples of real time. */
export const SHUTTLE_SPEEDS: readonly number[] = [1, 2, 4, 8, 16];

/**
 * Shuttles `scene` in `direction` — L forwards, J back.
 */
export function shuttlePlayback(world: World, scene: Entity, direction: 1 | -1): void {
	const playback = scene.get(Playback);
	if (!playback) return;

	const speed = playback.playing ? playback.speed : 0;

	// A speed off the ladder (indexOf -1) starts the climb over at its first
	// rung, which is also where a stop or a turnaround starts.
	const rung = Math.sign(speed) === direction
		? SHUTTLE_SPEEDS[Math.min(SHUTTLE_SPEEDS.indexOf(Math.abs(speed)) + 1, SHUTTLE_SPEEDS.length - 1)]!
		: SHUTTLE_SPEEDS[0]!;

	rewindIfParked(world, scene, direction);

	scene.set(Playback, { playing: true, speed: direction * rung });
	resumeAudioContext(world);
}
