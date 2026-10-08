/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

/**
 * The live `__inspect` — substituted for the throwing declaration in
 * @diffusionstudio/jsx (see "./runtime"), so a compiled `@inspect` declaration
 * resolves to a signal on the host's Solid instance. The composition reads it
 * through the rewritten references; the inspector reads and writes it through
 * the entry collected here. One signal, one graph: a set from the inspector
 * lands in the mounted entities without a remount.
 */

import { createSignal } from 'solid-js';

import type { Accessor } from 'solid-js';
import type { InspectDeclaration, InspectType, InspectValue } from '@diffusionstudio/jsx';

/**
 * One inspected variable of a mount: its identity (`file` and `name`, which is
 * how an edit of it is addressed to the source), how the inspector presents it
 * (`label`, `group` — derived from the authored `path`, or from the name), the
 * constraints its annotation put on it, and the signal itself.
 */
export interface InspectEntry {
	file: string;
	name: string;
	type: InspectType;
	label: string;
	/** The group segments the control is filed under; empty for ungrouped. */
	group: string[];
	min?: number;
	max?: number;
	step?: number;
	/** What a `select` chooses between, in the authored order. */
	options?: string[];
	/** What the source declared, before anyone touched the signal. */
	initial: InspectValue;
	/** The live value — what the composition reads, previews included. */
	get: Accessor<InspectValue>;
	/** Moves the live value alone: a hover preview, taken back on commit. */
	set: (value: InspectValue) => void;
	/**
	 * The last committed value — where the live value returns to when a
	 * preview ends, and the `previous` an edit of the variable inverts to.
	 */
	committed: Accessor<InspectValue>;
	/** Settles a value: the live signal and the committed one, together. */
	commit: (value: InspectValue) => void;
}

// Module evaluation is synchronous (see `evaluate`), so one slot is enough:
// whichever mount is evaluating right now is who the entries belong to.
let collecting: InspectEntry[] | null = null;

/**
 * Runs `fn` (a mount evaluating a bundle) collecting every `__inspect` call it
 * makes, in declaration order — imported modules first, the way CommonJS
 * evaluates them.
 */
export function collectInspect<T>(fn: () => T): { result: T; entries: InspectEntry[] } {
	const entries: InspectEntry[] = [];
	const previous = collecting;
	collecting = entries;
	try {
		return { result: fn(), entries };
	} finally {
		collecting = previous;
	}
}

/** `fontFamily` as a label: "Font Family". */
function prettify(name: string): string {
	return name
		.replace(/([a-z0-9])([A-Z])/g, '$1 $2')
		.replace(/[_-]+/g, ' ')
		.trim()
		.replace(/^./, (first) => first.toUpperCase());
}

export function __inspect(declaration: InspectDeclaration, initial: InspectValue): Accessor<InspectValue> {
	const [get, set] = createSignal(initial);
	const [committed, setCommitted] = createSignal(initial);
	const path = declaration.path ?? [];

	collecting?.push({
		file: declaration.file,
		name: declaration.name,
		type: declaration.type,
		label: path.at(-1) ?? prettify(declaration.name),
		group: path.slice(0, -1),
		...(declaration.min === undefined ? {} : { min: declaration.min }),
		...(declaration.max === undefined ? {} : { max: declaration.max }),
		...(declaration.step === undefined ? {} : { step: declaration.step }),
		...(declaration.options === undefined ? {} : { options: declaration.options }),
		initial,
		get,
		set,
		committed,
		commit: (value) => {
			set(value);
			setCommitted(value);
		},
	});

	return get;
}
