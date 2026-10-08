/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

import type { FontStyle } from '../constants';

/**
 * Defines the properties that are required
 * to load a new font
 */
export type FontSource = {
	/**
	 * Name of the Family
	 * @example 'Arial'
	 */
	family: string;
	/**
	 * Source of the Variant
	 * @example url(arial.ttf)
	 */
	source: string;
	/**
	 * Defines the font style
	 * @example 'italic'
	 */
	style?: FontStyle;
	/**
	 * The weight of the font
	 * @example '400'
	 */
	weight?: string;
};

/**
 * Defines a single font that has one or
 * more variants
 */
export type FontSources = {
	family: string;
	variants: FontSource[];
};
