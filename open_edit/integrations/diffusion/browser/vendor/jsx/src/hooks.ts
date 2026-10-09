/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

/**
 * The authoring hooks, as signatures. They read the host a project is mounted
 * into, which only exists inside the editor: when a project is mounted, the
 * renderer substitutes its own "@diffusionstudio/jsx" module (see
 * @diffusionstudio/reconciler) and these implementations are replaced by ones
 * bound to the live host. This package carries the declarations so project
 * sources type-check and get IntelliSense; calling them outside a mount
 * throws rather than silently returning a dead value.
 */

import type { Accessor } from "solid-js";

export type Ticker = {
  time: Accessor<number>;
  frame: Accessor<number>;
  delta: Accessor<number>;
  playing: Accessor<boolean>;
  hold: (work: Promise<unknown>) => void;
};

function hostOnly(name: string): never {
  throw new Error(
    `${name} is implemented by the editor's renderer and only works inside a mounted project.`,
  );
}

/**
 * Subscribes to the project's timeline: the playhead of the scene the mount's
 * root lives in (or is), pushed by the host once per playback tick. Each
 * accessor only propagates when its value changes, so a paused scene re-runs
 * nothing and `frame()` consumers update at most once per frame. Values move
 * while the reactive graph is alive: a mount stays live, and export, capture,
 * and reload each re-execute the module and drive the ticker themselves.
 *
 * `hold` is the other half of that: because a mount of its own is what an
 * export or a capture draws, a project's own async work (a mesh, a texture,
 * a fetch a layout is decided by) races the first frames, which are sampled
 * as soon as the module has rendered. Handing the promise to `hold` keeps
 * those frames waiting for it. Live playback collects nothing, so a held
 * promise costs the editor nothing.
 */
export function useTicker(): Ticker {
  return hostOnly("useTicker");
}

/**
 * Subscribes to the host's rasterization density: how many device pixels one
 * composition pixel is drawn with, camera zoom excluded. `1` where nothing
 * scales, the display's pixel ratio in the live editor, and the export's
 * resolution factor while a scene encodes above (or below) its native size.
 * What a `<surface>` reads to size its bitmap so hand-drawn pixels stay
 * sharp at any output size.
 *
 * Reactive, not a constant: an offline mount starts at `1` and learns the
 * real factor before the first frame is sampled, so read it inside the
 * effect that sizes and draws rather than once at mount.
 */
export function useResolution(): Accessor<number> {
  return hostOnly("useResolution");
}
