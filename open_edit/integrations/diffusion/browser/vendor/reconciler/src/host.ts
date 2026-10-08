/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

/**
 * The host document the universal renderer writes into. The editor implements
 * this interface directly over its ECS world, so rendering a project builds
 * real composition entities — there is no intermediate staged tree. The
 * operations mirror `createRenderer`'s host config one to one; node values are
 * opaque to the renderer.
 */

/**
 * One reading of the host's timeline clock, local to the mounted project:
 * the playhead of the scene the mount's root lives in (or is). Values only
 * move for live mounts; the host pushes a fresh reading once per playback
 * tick.
 */
export type ProjectTick = {
  /** Playhead in seconds (sub-frame precision while playing). */
  time: number;
  /** Playhead in frames at the host frame rate. */
  frame: number;
  /** Seconds advanced since the previous tick: 0 while paused, negative on a backward scrub or loop. */
  delta: number;
  /** Whether the scene is currently playing. */
  playing: boolean;
};

export interface ProjectDocument<N = unknown> {
  stage: N;
  createElement(tag: string): N;
  createTextNode(text: string): N;
  replaceText(node: N, text: string): void;
  isTextNode(node: N): boolean;
  setProperty(node: N, name: string, value: unknown): void;
  insertNode(parent: N, node: N, anchor?: N): void;
  removeNode(parent: N, node: N): void;
  getParentNode(node: N): N | undefined;
  getFirstChild(node: N): N | undefined;
  getNextSibling(node: N): N | undefined;
  tick?(): ProjectTick;
  hold?(work: Promise<unknown>): void;
  resolution?(): number;
  applyRef?(node: N, ref: (target: unknown) => void): void;
}
