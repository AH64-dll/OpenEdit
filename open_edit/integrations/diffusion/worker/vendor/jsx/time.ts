/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

import type { Time } from "./types";

/** Frames per second of the canonical `Time` frame unit ("30f"). */
export const TIME_FPS = 30;

/**
 * Parses a `Time` value into seconds: plain numbers are seconds, "30f" is
 * frames at `TIME_FPS`, "MM:SS" / "HH:MM:SS" are clock strings. Values may be
 * negative. Returns undefined for anything unparsable.
 */
export function parseTime(value: Time | string | null | undefined): number | undefined {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : undefined;
  }

  const str = value?.trim();
  if (typeof str !== "string" || str.length === 0) {
    return undefined;
  }

  // Frames, e.g. "-30f".
  if (/^-?\d+(?:\.\d+)?f$/i.test(str)) {
    return parseFloat(str) / TIME_FPS;
  }

  // MM:SS or HH:MM:SS.
  if (str.includes(":")) {
    const negative = str.startsWith("-");
    const parts = str.replace(/^-/, "").split(":").map(Number);

    if (parts.some((n) => !Number.isFinite(n))) {
      return undefined;
    }

    let seconds: number;
    if (parts.length === 2) {
      seconds = parts[0]! * 60 + parts[1]!;
    } else if (parts.length === 3) {
      seconds = parts[0]! * 3600 + parts[1]! * 60 + parts[2]!;
    } else {
      return undefined;
    }

    return negative ? -seconds : seconds;
  }

  // Plain seconds (may be fractional).
  const seconds = parseFloat(str);
  return Number.isFinite(seconds) ? seconds : undefined;
}
