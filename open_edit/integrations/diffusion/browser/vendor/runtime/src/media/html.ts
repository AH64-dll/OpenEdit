/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

export function isHtmlInCanvasSupported(): boolean {
	return typeof CanvasRenderingContext2D !== 'undefined'
		&& 'drawElementImage' in CanvasRenderingContext2D.prototype;
}

/**
 * Resolves after the browser's next rendering update (style/layout/paint) has completed.
 */
export function nextRenderingUpdate(): Promise<void> {
	return new Promise(resolve => {
		// timeout in case requestAnimationFrame is not called
		const timeout = setTimeout(resolve, 250);

		requestAnimationFrame(() => {
			clearTimeout(timeout);
			setTimeout(resolve, 0);
		});
	});
}

/** Resolve asynchronously loaded resources below an HTML paint root. */
export function whenHtmlReady(root: HTMLElement, timeInSeconds: number): Promise<void> {
	for (const animation of root.getAnimations({ subtree: true })) {
		if (animation.playState !== 'paused') animation.pause();
		animation.currentTime = timeInSeconds * 1000;
	}

	const pending: Promise<unknown>[] = [document.fonts.ready];
	for (const image of root.querySelectorAll('img')) {
		if (image.complete) continue;
		pending.push(image.decode().catch(() => undefined));
	}

	return Promise.all(pending).then(() => nextRenderingUpdate());
}
