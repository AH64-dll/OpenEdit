/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

// Timeline view read path. The Timeline trait on a scene is where its
// timeline canvas is looking; the editor's own reads go through its view
// helpers, and this is the round-trip form. Writes live in
// actions/timeline-view.ts.

import { FrameRate, Timeline } from '../traits';
import { store } from '../world/store';

import type { Entity, World } from 'koota';

/**
 * A scene's timeline viewport as `[zoom, x, y]`: `zoom` in pixels per second
 * of timeline, `x` the horizontal scroll in seconds, `y` the vertical scroll
 * in pixels. The form a project writes (`<scene timeline={…}>`): seconds
 * rather than the frames the trait holds, so the value survives a change of
 * frame rate.
 */
export type TimelineView = [zoom: number, x: number, y: number];

/** The scene's view in file form, or null while it has never been looked at. */
export function getTimelineView(world: World, scene: Entity): TimelineView | null {
	if (!scene.has(Timeline)) return null;

	const fps = world.get(FrameRate)?.value ?? 30;
	const view = store(world, Timeline);
	const eid = scene.id();

	return [(view.resolution[eid] ?? 1) * fps, (view.scrollX[eid] ?? 0) / fps, view.scrollY[eid] ?? 0];
}
