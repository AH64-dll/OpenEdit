/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

// Timeline view write path. Written through the store rather than
// `entity.set`, the way the editor's own scroll handlers write it: where the
// timeline is looking is not an edit of the project, so nothing observes it.

import { FrameRate, Timeline } from '../traits';
import { store } from '../world/store';

import type { Entity, World } from 'koota';
import type { TimelineView } from '../queries/timeline-view';

/**
 * Restores a view `getTimelineView` reported: zoom in pixels per second,
 * horizontal scroll in seconds, vertical scroll in pixels. Unclamped, like
 * `setCameraMatrix`: the gestures that produce one have already been held to
 * the limits. A zoom of nothing (or less) would collapse the timeline onto
 * one column, so a view saying that is refused whole.
 */
export function setTimelineView(world: World, scene: Entity, [zoom, x, y]: TimelineView): void {
	if (!(zoom > 0) || !Number.isFinite(zoom) || !Number.isFinite(x) || !Number.isFinite(y)) return;

	const fps = world.get(FrameRate)?.value ?? 30;
	if (!scene.has(Timeline)) scene.add(Timeline);

	const view = store(world, Timeline);
	const eid = scene.id();
	view.resolution[eid] = zoom / fps;
	view.scrollX[eid] = x * fps;
	view.scrollY[eid] = y;
}
