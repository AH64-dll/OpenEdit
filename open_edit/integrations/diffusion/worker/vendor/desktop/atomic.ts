/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

// Writes that land whole. Anything may be reading a project's files while the
// app writes them — a compile, the user's editor, the watcher reading a file
// back to see whether it really changed — and a reader that catches a file
// halfway through a write sees source no one wrote. So a write goes to a temp
// file beside its target and is renamed over it, which the filesystem does in
// one step.

import { rename, unlink, writeFile } from "node:fs/promises";
import { basename, dirname, join } from "node:path";

/**
 * The prefix every temp file the app writes carries. Recognisable rather than
 * unique, so the project watcher can ignore the whole class of them without
 * anyone having to declare each one as it is written.
 */
export const TEMP_PREFIX = ".dstmp-";

/** Whether `path` — of any form — names one of our temp files. */
export const isTempPath = (path: string): boolean => basename(path).startsWith(TEMP_PREFIX);

let sequence = 0;

/**
 * A free path beside `path` to write at until the content is whole. Beside it
 * rather than in the system's temp folder, because a rename is only atomic
 * within a filesystem.
 */
export function tempPathFor(path: string): string {
  return join(dirname(path), `${TEMP_PREFIX}${basename(path)}.${process.pid}-${++sequence}`);
}

/**
 * Writes `text` to `path` as one step: a temp file beside it, renamed over it.
 * A failed write takes its temp file with it.
 */
export async function writeFileAtomic(path: string, text: string): Promise<void> {
  const temp = tempPathFor(path);
  try {
    await writeFile(temp, text, "utf8");
    await rename(temp, path);
  } catch (error) {
    await unlink(temp).catch(() => { });
    throw error;
  }
}
