/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

/**
 * Attempt to execute a function and return the result or the error it threw.
 */
export function attempt<T>(fn: () => T): { result: T } | { error: Error } {
	try {
		return { result: fn() };
	} catch (error) {
		if (error instanceof Error) {
			return { error };
		}
		return { error: new Error('Unknown error') };
	}
}

export class AsyncMutex {
	currentPromise = Promise.resolve();

	async acquire() {
		let resolver: () => void;
		const nextPromise = new Promise<void>(resolve => {
			resolver = resolve;
		});

		const currentPromiseAlias = this.currentPromise;
		this.currentPromise = nextPromise;

		await currentPromiseAlias;

		return resolver!;
	}
}
