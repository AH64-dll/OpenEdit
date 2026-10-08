/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

// Packed 0xRRGGBB color helpers (subset of the app's utils/color.ts that the
// renderer and shader uniforms need; UI-facing conversions stay app-side).

import { colord } from 'colord';

import { clamp } from '../math/common';

const NAMED_COLORS: Record<string, string> = {
	red: 'FF0000',
	green: '008000',
	blue: '0000FF',
	white: 'FFFFFF',
	black: '000000',
	yellow: 'FFFF00',
	cyan: '00FFFF',
	magenta: 'FF00FF',
	orange: 'FFA500',
	purple: '800080',
	pink: 'FFC0CB',
	gray: '808080',
	grey: '808080',
	brown: 'A52A2A',
	lime: '00FF00',
	navy: '000080',
	teal: '008080',
	maroon: '800000',
	olive: '808000',
	aqua: '00FFFF',
	coral: 'FF7F50',
	salmon: 'FA8072',
	gold: 'FFD700',
	silver: 'C0C0C0',
	indigo: '4B0082',
	violet: 'EE82EE',
	crimson: 'DC143C',
	tomato: 'FF6347',
	khaki: 'F0E68C',
	plum: 'DDA0DD',
	orchid: 'DA70D6',
	tan: 'D2B48C',
	beige: 'F5F5DC',
	ivory: 'FFFFF0',
	lavender: 'E6E6FA',
	turquoise: '40E0D0',
	chartreuse: '7FFF00',
	sienna: 'A0522D',
	peru: 'CD853F',
	firebrick: 'B22222',
	skyblue: '87CEEB',
	hotpink: 'FF69B4',
	mint: '3EB489',
};

/**
 * Parses any colord-compatible input (hex with or without `#`, short hex,
 * `rgb()`, `hsl()`, named colors, etc.) into a numeric hex color (0xRRGGBB).
 * Arbitrary strings fall back to Figma-style hex normalization: strip non-hex
 * characters, then repeat/pad to six digits (empty input returns null).
 */
export function parseColor(input: unknown): number | null {
	if (typeof input === 'number') {
		return Number.isFinite(input) ? input & 0xFFFFFF : null;
	}

	if (typeof input !== 'string') {
		return null;
	}

	const trimmed = input.trim();
	if (trimmed.length === 0) return null;

	const named = NAMED_COLORS[trimmed.toLowerCase()];
	if (named) {
		return parseInt(named, 16);
	}

	const c = colord(trimmed);
	if (c.isValid()) {
		const { r, g, b } = c.toRgb();
		return rgbToColor(r, g, b);
	}

	const hex = trimmed.replace(/[^0-9A-Fa-f]/g, '');
	if (hex.length === 0) return null;

	let normalized: string;
	if (hex.length === 1) normalized = hex.repeat(6);
	else if (hex.length === 2) normalized = hex.repeat(3);
	else if (hex.length === 3) normalized = hex.split('').map((ch) => ch + ch).join('');
	else if (hex.length === 4) normalized = hex + '00';
	else if (hex.length === 5) normalized = hex + '0';
	else if (hex.length === 6) normalized = hex;
	else normalized = hex.slice(0, 6);

	return parseInt(normalized.toUpperCase(), 16);
}

/**
 * Converts a numeric hex color (0xRRGGBB) to a CSS hex string (#RRGGBB).
 */
export function colorToHex(color: number): string {
	return '#' + ((1 << 24) | (color & 0xFFFFFF)).toString(16).slice(1).toUpperCase();
}

/**
 * A CSS color for `color` at `opacity`: the hex when opaque, else an rgba().
 */
export function colorToCss(color: number, opacity: number): string {
	if (opacity >= 1) return colorToHex(color);

	const r = (color >> 16) & 0xFF;
	const g = (color >> 8) & 0xFF;
	const b = color & 0xFF;
	return `rgba(${r},${g},${b},${clamp(opacity, 0, 1)})`;
}

/**
 * Packs RGB channel values (0-255) into a numeric hex color (0xRRGGBB).
 */
export function rgbToColor(r: number, g: number, b: number): number {
	const rc = clamp(Math.round(r), 0, 255);
	const gc = clamp(Math.round(g), 0, 255);
	const bc = clamp(Math.round(b), 0, 255);
	return (rc << 16) | (gc << 8) | bc;
}

/**
 * Unpacks a numeric hex color (0xRRGGBB) into RGB channel values (0-255).
 */
export function colorToRgb(color: number): { r: number; g: number; b: number } {
	return {
		r: (color >> 16) & 0xFF,
		g: (color >> 8) & 0xFF,
		b: color & 0xFF,
	};
}
