/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

/**
 * What a compiled bundle sees as "@diffusionstudio/jsx".
 *
 * The npm package under that name is authoring-only — types, pure helpers, and
 * hooks that throw because they have no host to read. A project never resolves
 * it from node_modules at runtime: the desktop compile marks the specifier
 * external (`moduleName` for babel-preset-solid's universal transform), and
 * `evaluate` binds it to this object instead. So the module a project imports
 * is the authoring surface with the host-bound implementations layered over
 * it: the renderer's element operations, the compile-target components, and
 * live `useTicker` in place of the throwing declaration.
 *
 * Order matters — the renderer bindings must come last so they win.
 */

import * as authoring from '@diffusionstudio/jsx';

import * as elements from './elements';
import { __inspect } from './inspect';
import {
	createComponent,
	createElement,
	createTextNode,
	effect,
	insert,
	insertNode,
	memo,
	mergeProps,
	render,
	setProp,
	spread,
	use,
	useResolution,
	useTicker,
} from './renderer';

export const JSX_RUNTIME = {
	...authoring,
	...elements,
	render,
	effect,
	memo,
	createComponent,
	createElement,
	createTextNode,
	insertNode,
	insert,
	spread,
	setProp,
	mergeProps,
	use,
	useResolution,
	useTicker,
	__inspect,
};
