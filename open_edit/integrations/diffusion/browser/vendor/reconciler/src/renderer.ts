/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

import { createContext, createMemo, useContext } from "solid-js";
import { createRenderer } from "solid-js/universal";

import type { Accessor, JSX } from "solid-js";
import type { Ticker } from "@diffusionstudio/jsx";
import type { ProjectDocument } from "./host";

// Compiled project modules call the static runtime exports below
// (babel-preset-solid in `universal` mode with a fixed moduleName), so the
// renderer must be a module-level singleton.
const DocumentContext = createContext<ProjectDocument | null>(null);

let currentDocument: ProjectDocument | null = null;

function doc(): ProjectDocument {
  const document = useContext(DocumentContext) ?? currentDocument;
  if (document === null) {
    throw new Error("No active mount — elements can only be created while a project renders");
  }
  return document;
}

const renderer = createRenderer<unknown>({
  createElement(tag: string): unknown {
    return doc().createElement(tag);
  },
  createTextNode(value: string): unknown {
    return doc().createTextNode(String(value));
  },
  replaceText(textNode: unknown, value: string): void {
    doc().replaceText(textNode, String(value));
  },
  isTextNode(node: unknown): boolean {
    return doc().isTextNode(node);
  },
  setProperty(node: unknown, name: string, value: unknown): void {
    doc().setProperty(node, name, value);
  },
  insertNode(parent: unknown, node: unknown, anchor?: unknown): void {
    doc().insertNode(parent, node, anchor);
  },
  removeNode(parent: unknown, node: unknown): void {
    doc().removeNode(parent, node);
  },
  getParentNode(node: unknown): unknown {
    return doc().getParentNode(node);
  },
  getFirstChild(node: unknown): unknown {
    return doc().getFirstChild(node);
  },
  getNextSibling(node: unknown): unknown {
    return doc().getNextSibling(node);
  },
});

export const {
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
} = renderer;

/**
 * Ref application (compiled `ref={fn}`). Hosts that materialize elements
 * lazily route refs through `applyRef` so the callback receives the backing
 * object once it exists; hosts without `applyRef` keep the renderer's
 * immediate call with the host node.
 */
export function use(fn: (target: unknown, arg?: unknown) => void, node: unknown, arg?: unknown): unknown {
  const document = doc();
  if (document.applyRef) {
    document.applyRef(node, fn);
    return node;
  }
  return renderer.use(fn, node, arg);
}

/**
 * The live `useTicker` — substituted for the throwing declaration in
 * @diffusionstudio/jsx (see "./runtime"), so a mounted project's import
 * resolves to this one. Each accessor only propagates when its value changes,
 * so a paused scene re-runs nothing.
 *
 * `hold` is the host's frame barrier, or a no-op where the host has none:
 * a project holding work in a document that draws in realtime is not an
 * error, there is simply nothing there that waits.
 */
export function useTicker(): Ticker {
  const document = doc();
  if (!document.tick) {
    throw new Error("useTicker: this host does not provide a timeline clock");
  }

  const tick = document.tick.bind(document);
  const hold = document.hold?.bind(document) ?? (() => {});
  return {
    time: createMemo(() => tick().time),
    frame: createMemo(() => tick().frame),
    delta: createMemo(() => tick().delta),
    playing: createMemo(() => tick().playing),
    hold,
  };
}

/**
 * The live `useResolution` — the host's rasterization density as a memo,
 * a constant 1 where the host reports none: a project reading it in a
 * document that never scales is not an error, everything there is drawn
 * pixel for pixel.
 */
export function useResolution(): Accessor<number> {
  const document = doc();
  const read = document.resolution?.bind(document);
  return createMemo(() => read?.() ?? 1);
}

/**
 * Runs `fn` with `document` as the one the static runtime exports write into.
 * Anything creating elements outside a project render — a host inserting
 * elements of its own — goes through here.
 */
export function withDocument<N, T>(document: ProjectDocument<N>, fn: () => T): T {
  const previous = currentDocument;
  currentDocument = document as ProjectDocument;
  try {
    return fn();
  } finally {
    currentDocument = previous;
  }
}

/**
 * Host entry point: renders a project component directly into `document`.
 * Mounting is synchronous — the document is fully written when this returns.
 */
export function renderProject<N>(project: () => unknown, document: ProjectDocument<N>): () => void {
  return withDocument(document, () =>
    render(() => createComponent(DocumentContext.Provider, {
      value: document as ProjectDocument,
      get children() {
        return createComponent(project, {}) as JSX.Element;
      },
    }), document.stage),
  );
}
