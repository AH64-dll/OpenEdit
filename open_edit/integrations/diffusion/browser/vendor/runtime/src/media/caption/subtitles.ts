/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

import type { Transcript } from '@diffusionstudio/assets';

const TIMESTAMP_RE = /(?:\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{1,3}/g;

function parseTimestamp(raw: string): number {
  return raw
    .replace(',', '.')
    .split(':')
    .reduce((acc, part) => acc * 60 + Number(part), 0);
}

/**
 * Parses SRT or WebVTT text into a `Transcript`. Each cue becomes one segment
 * (a sentence boundary for grouping). Cues carry no word timings, so each
 * word's window is synthesized proportional to its length within the cue.
 */
export function parseSubtitles(text: string): Transcript {
  const transcript: Transcript = [];
  const blocks = text.replace(/^\uFEFF/, '').replace(/\r\n?/g, '\n').split(/\n{2,}/);

  for (const block of blocks) {
    const lines = block.split('\n');
    const timingIndex = lines.findIndex((line) => line.includes('-->'));
    if (timingIndex === -1) continue; // WEBVTT header, NOTE/STYLE/REGION blocks, stray indices

    const timestamps = lines[timingIndex].match(TIMESTAMP_RE);
    if (!timestamps || timestamps.length < 2) continue;
    const start = parseTimestamp(timestamps[0]);
    const end = parseTimestamp(timestamps[1]);
    if (!(end > start)) continue;

    // Strip inline markup: HTML/VTT tags (<i>, <c.class>, <00:01.000>) and
    // SSA-style overrides ({\an8}).
    const content = lines
      .slice(timingIndex + 1)
      .join(' ')
      .replace(/<[^>]*>/g, '')
      .replace(/\{[^}]*\}/g, '');

    const tokens = content.split(/\s+/).filter(Boolean);
    if (tokens.length === 0) continue;

    const total = tokens.reduce((acc, token) => acc + token.length, 0);
    const duration = end - start;
    let elapsed = 0;
    const words = tokens.map((token) => {
      const wordStart = start + (elapsed / total) * duration;
      elapsed += token.length;
      return { text: token, start: wordStart, end: start + (elapsed / total) * duration };
    });

    transcript.push({ text: tokens.join(' '), words });
  }

  return transcript.sort((a, b) => a.words[0].start - b.words[0].start);
}
