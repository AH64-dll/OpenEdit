/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

/**
 * The inspect annotation: how a project marks a top-level `const` as editable
 * from the editor's inspector.
 *
 *     // A JSDoc comment on the declaration:  @inspect number min=0 max=100 step=1
 *     const padding = 24;
 *
 * The compile step reads the annotation, turns the declaration into a signal
 * (`__inspect`), and rewrites every reference into a call of it — so the
 * inspector can move the value live, and the editor writes what it settles on
 * back into the initializer. The variable is addressed by file and name;
 * nothing about it needs an id.
 *
 * `path="Typography/Font"` is presentation only: the last segment is the
 * control's label, the segments before it the group it is filed under. Without
 * it, the label is the variable's own name, prettified, and the control is
 * ungrouped. `label="Font"` names the control without grouping it.
 *
 * The initializer must be a plain literal — a `number` a numeric one, a
 * `boolean` `true`/`false`, the string types a string (a `select`'s one of its
 * `options="a,b,c"`) — since it is what the editor overwrites. Because the
 * rewrite is per file, an annotated variable cannot be exported: an importer
 * would receive the accessor where it expects the value.
 */

import type { Accessor } from "solid-js";

/** The JSDoc tag, without the `@`. */
export const INSPECT_TAG = "inspect";

/** The controls an annotation can ask for, keyed by how the value is edited. */
export const INSPECT_TYPES = ["number", "color", "text", "font", "boolean", "select"] as const;

export type InspectType = (typeof INSPECT_TYPES)[number];

/** What an inspected variable can hold: what its literal initializer can be. */
export type InspectValue = string | number | boolean;

/**
 * An annotated declaration as the compile step spells it into the bundle —
 * everything the annotation and the declaration said, verbatim. `path` is the
 * authored `path` (or `label`) split into segments; presentation derives from
 * it at mount.
 */
export interface InspectDeclaration {
  /** Project-relative file the variable is declared in. */
  file: string;
  /** The variable's own name — with `file`, its identity. */
  name: string;
  type: InspectType;
  path?: string[];
  min?: number;
  max?: number;
  step?: number;
  /** What a `select` chooses between, in the authored order. */
  options?: string[];
}

function hostOnly(name: string): never {
  throw new Error(
    `${name} is implemented by the editor's renderer and only works inside a mounted project.`,
  );
}

/**
 * What an `@inspect` declaration compiles into: a signal the inspector shares
 * with the composition. Never authored by hand — the compile step injects the
 * call and rewrites the variable's references into calls of the accessor; this
 * declaration exists so the substituted module (see @diffusionstudio/reconciler)
 * has a signature to stand in for.
 */
export function __inspect(declaration: InspectDeclaration, initial: InspectValue): Accessor<InspectValue> {
  void declaration;
  void initial;
  return hostOnly("__inspect");
}
