/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

/**
 * Axis-Aligned Bounding Box utilities.
 */

import type { Mat2D } from './matrix2d';

export type AABB = { minX: number; minY: number; maxX: number; maxY: number };

/**
 * Compute the world-space AABB of a rectangle [0,0]→[w,h]
 * transformed by a 2D affine matrix.
 */
export function aabbFromTransformedRect(mat: Mat2D, w: number, h: number): AABB {
	const { a, b, c, d, e, f } = mat;

	// Transform 4 corners: (0,0), (w,0), (w,h), (0,h)
	const x0 = e,                 y0 = f;
	const x1 = a * w + e,         y1 = b * w + f;
	const x2 = a * w + c * h + e, y2 = b * w + d * h + f;
	const x3 = c * h + e,         y3 = d * h + f;

	return {
		minX: Math.min(x0, x1, x2, x3),
		minY: Math.min(y0, y1, y2, y3),
		maxX: Math.max(x0, x1, x2, x3),
		maxY: Math.max(y0, y1, y2, y3),
	};
}

/** Test whether two AABBs overlap. */
export function aabbsIntersect(a: AABB, b: AABB): boolean {
	return !(
		a.maxX < b.minX ||
		a.minX > b.maxX ||
		a.maxY < b.minY ||
		a.minY > b.maxY
	);
}

// ─── Polygon geometry ───────────────────────────────────────────

export type Point = { x: number; y: number };

/** An axis-aligned rectangle by origin and size (AABB by min/max corners). */
export type Rect = { x: number; y: number; width: number; height: number };

/** Four corners of a transformed rect: [TL, TR, BR, BL]. */
export type Quad = [Point, Point, Point, Point];

/** Get the four world-space corners of a rect [0,0]→[w,h] through a Mat2D. */
export function rectToQuad(mat: Mat2D, w: number, h: number): Quad {
	const { a, b, c, d, e, f } = mat;
	return [
		{ x: e, y: f },
		{ x: a * w + e, y: b * w + f },
		{ x: a * w + c * h + e, y: b * w + d * h + f },
		{ x: c * h + e, y: d * h + f },
	];
}

/** Transform a single point through a Mat2D. */
export function transformPoint(mat: Mat2D, px: number, py: number): Point {
	return {
		x: mat.a * px + mat.c * py + mat.e,
		y: mat.b * px + mat.d * py + mat.f,
	};
}

/** Invert a Mat2D. */
export function invert2D(m: Mat2D): Mat2D {
	const { a, b, c, d, e, f } = m;
	const det = a * d - b * c;

	const inv = 1 / det;
	return {
		a: d * inv,
		b: -b * inv,
		c: -c * inv,
		d: a * inv,
		e: (c * f - d * e) * inv,
		f: (b * e - a * f) * inv,
	};
}

/** Point-in-polygon test (ray casting). */
export function pointInQuad(px: number, py: number, q: Quad): boolean {
	let inside = false;
	for (let i = 0, j = 3; i < 4; j = i++) {
		const xi = q[i].x, yi = q[i].y;
		const xj = q[j].x, yj = q[j].y;
		if (((yi > py) !== (yj > py)) && (px < (xj - xi) * (py - yi) / (yj - yi) + xi)) {
			inside = !inside;
		}
	}
	return inside;
}

/** 
 * Test whether two quads intersect (vertex containment check).
 */
export function quadsIntersect(a: Quad, b: Quad): boolean {
	for (let i = 0; i < 4; i++) {
		if (pointInQuad(a[i].x, a[i].y, b)) return true;
		if (pointInQuad(b[i].x, b[i].y, a)) return true;
	}
	return false;
}

/** 
 * Test whether `outer` wholly contains `inner`. Quads are transformed rects,
 * so both are convex and corner containment is containment.
 */
export function quadContainsQuad(outer: Quad, inner: Quad): boolean {
	for (let i = 0; i < 4; i++) {
		if (!pointInQuad(inner[i].x, inner[i].y, outer)) return false;
	}
	return true;
}

/** Center point of a quad. */
export function quadCenter(q: Quad): Point {
	return {
		x: (q[0].x + q[1].x + q[2].x + q[3].x) / 4,
		y: (q[0].y + q[1].y + q[2].y + q[3].y) / 4,
	};
}
