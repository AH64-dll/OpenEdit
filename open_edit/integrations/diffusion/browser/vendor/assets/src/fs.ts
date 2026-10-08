/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

// The file system a project lives in, as far as the asset library needs it.
// The desktop implements this over IPC to the main process (real files, the
// manifest as YAML); a browser host would implement it over a
// FileSystemDirectoryHandle. The library never joins paths itself: a `path`
// is project-relative, a `source` is either that or an absolute OS path, and
// the host knows which is which.

import type { Manifest } from './manifest';
import type { AssetStat } from './types';

export interface FsEntry {
	name: string;
	kind: 'file' | 'directory';
	size: number;
	/** Modification time in ms since the epoch. */
	mtime: number;
	/**
	 * Set when the entry is a symlink. `kind` is still what it points at — a
	 * link is listed like the file or folder it stands for — but where that
	 * lies is `realPath`'s to say.
	 */
	link?: boolean;
}

export interface ProjectFS {
	/** The manifest as plain data, or null when the project has none yet. */
	readManifest(): Promise<unknown>;
	writeManifest(manifest: Manifest): Promise<void>;
	/** Entries of a directory (project-relative or absolute); [] when missing. */
	list(source: string): Promise<FsEntry[]>;
	/** Size and mtime of a file, or null when it does not exist. */
	stat(source: string): Promise<AssetStat | null>;
	/** The bytes of a file (project-relative or absolute). */
	file(source: string): Promise<File>;
	/** Writes a file inside the project, creating parent directories. */
	write(path: string, data: Blob): Promise<void>;
	/** Removes a file or directory inside the project; missing is fine. */
	remove(path: string): Promise<void>;
	/**
	 * Where a path really is, symlinks resolved; null when it does not exist.
	 * Optional: a host that has no such notion (a browser) leaves it out, and
	 * a walk that cannot resolve a link simply follows it.
	 */
	realPath?(source: string): Promise<string | null>;
	/** The absolute location of a project-relative path, when the host has one. */
	absolute?(path: string): string;
	/**
	 * The path of a File the user picked or dropped, when the host can tell
	 * (Electron can; a browser cannot). What `import` links to.
	 */
	pathOf?(file: File): string | null;
}
