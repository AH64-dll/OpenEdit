/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

import { ALL_FORMATS, AudioSampleSink, BlobSource, Input } from 'mediabunny';

import { assert } from '../utils/assert';
import { getAssetFile } from '../actions/assets';

import type { Asset } from '@diffusionstudio/assets';

// Envelope sample rate. 500 Hz → 2 ms resolution (well under one video frame),
// and keeps the FFT small enough for multi-minute clips. Parabolic
// interpolation around the peak refines below one bin.
const SYNC_ENVELOPE_RATE_HZ = 500;
// Require at least this much overlapping audio for a lag to be considered.
const SYNC_MIN_OVERLAP_SEC = 1;
// Below this correlation the match is treated as no match, and we fail loudly
// rather than return a confident-looking but meaningless offset.
const SYNC_NO_MATCH_FLOOR = 0.1;

export type AudioSyncResult = {
  // Place the audio at: audioStart = videoStart + offsetSeconds.
  // Positive = the recording started after the camera rolled.
  offsetSeconds: number;
  confidence: number; // 0..1 (clamped Pearson correlation at the best lag)
};

// RMS energy envelope of an asset's primary audio track, at `rate` bins/sec.
async function extractAudioEnvelope(asset: Asset, rate: number): Promise<Float32Array> {
  const blob = await getAssetFile(asset);
  const input = new Input({ formats: ALL_FORMATS, source: new BlobSource(blob) });
  try {
    const track = await input.getPrimaryAudioTrack();
    assert(track, `Asset ${asset.id} has no audio track to sync.`);
    const sink = new AudioSampleSink(track);
    const bins: number[] = [];
    for await (const sample of sink.samples()) {
      try {
        const size = sample.allocationSize({ format: 'f32', planeIndex: 0 });
        const floats = new Float32Array(size / Float32Array.BYTES_PER_ELEMENT);
        sample.copyTo(floats, { format: 'f32', planeIndex: 0 });

        const numChannels = sample.numberOfChannels;
        const numFrames = floats.length / numChannels;
        const targetBins = Math.max(1, Math.round(sample.duration * rate));
        const ratio = numFrames / targetBins;

        for (let i = 0; i < targetBins; i++) {
          const start = Math.floor(i * ratio);
          const end = Math.max(start + 1, Math.floor((i + 1) * ratio));
          let sumSq = 0;
          let count = 0;
          for (let f = start; f < end && f < numFrames; f++) {
            for (let ch = 0; ch < numChannels; ch++) {
              const v = floats[f * numChannels + ch];
              sumSq += v * v;
              count++;
            }
          }
          bins.push(count ? Math.sqrt(sumSq / count) : 0);
        }
      } finally {
        sample.close();
      }
    }
    return Float32Array.from(bins);
  } finally {
    input.dispose();
  }
}

function nextPow2(n: number): number {
  let p = 1;
  while (p < n) p <<= 1;
  return p;
}

// In-place iterative radix-2 Cooley-Tukey FFT (inverse when `invert`).
function fft(re: Float64Array, im: Float64Array, invert: boolean): void {
  const n = re.length;
  for (let i = 1, j = 0; i < n; i++) {
    let bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) {
      const tr = re[i]; re[i] = re[j]; re[j] = tr;
      const ti = im[i]; im[i] = im[j]; im[j] = ti;
    }
  }
  for (let len = 2; len <= n; len <<= 1) {
    const ang = ((invert ? 2 : -2) * Math.PI) / len;
    const wr = Math.cos(ang);
    const wi = Math.sin(ang);
    for (let i = 0; i < n; i += len) {
      let cwr = 1;
      let cwi = 0;
      for (let k = 0; k < len >> 1; k++) {
        const a = i + k;
        const b = a + (len >> 1);
        const vr = re[b] * cwr - im[b] * cwi;
        const vi = re[b] * cwi + im[b] * cwr;
        re[b] = re[a] - vr; im[b] = im[a] - vi;
        re[a] += vr; im[a] += vi;
        const ncwr = cwr * wr - cwi * wi;
        cwi = cwr * wi + cwi * wr;
        cwr = ncwr;
      }
    }
  }
  if (invert) {
    for (let i = 0; i < n; i++) { re[i] /= n; im[i] /= n; }
  }
}

// Linear cross-correlation via FFT. Returns cc where cc[m] = Σ a[i]·b[i+m]
// (negative lags wrap to the high indices; safe because of zero padding).
function crossCorrelate(a: Float32Array, b: Float32Array): Float64Array {
  const n = nextPow2(a.length + b.length);
  const ar = new Float64Array(n);
  const ai = new Float64Array(n);
  const br = new Float64Array(n);
  const bi = new Float64Array(n);
  ar.set(a);
  br.set(b);
  fft(ar, ai, false);
  fft(br, bi, false);
  // conj(FA) .* FB
  for (let k = 0; k < n; k++) {
    const cr = ar[k] * br[k] + ai[k] * bi[k];
    const ci = ar[k] * bi[k] - ai[k] * br[k];
    ar[k] = cr;
    ai[k] = ci;
  }
  fft(ar, ai, true);
  return ar; // real part holds the correlation
}

function prefixSums(x: Float32Array): { sum: Float64Array; sumSq: Float64Array } {
  const sum = new Float64Array(x.length + 1);
  const sumSq = new Float64Array(x.length + 1);
  for (let i = 0; i < x.length; i++) {
    sum[i + 1] = sum[i] + x[i];
    sumSq[i + 1] = sumSq[i] + x[i] * x[i];
  }
  return { sum, sumSq };
}

const offsetCache = new Map<string, Promise<AudioSyncResult>>();

export function computeAudioSyncOffsetCached(a: Asset, b: Asset): Promise<AudioSyncResult> {
  const key = `${a.id}:${b.id}`;
  const cached = offsetCache.get(key);
  if (cached) return cached;
  const promise = computeAudioSyncOffset(a, b);
  offsetCache.set(key, promise);
  promise.catch(() => offsetCache.delete(key));
  return promise;
}

export async function computeAudioSyncOffset(
  audioAsset: Asset,
  videoAsset: Asset,
): Promise<AudioSyncResult> {
  const rate = SYNC_ENVELOPE_RATE_HZ;
  const A = await extractAudioEnvelope(audioAsset, rate);
  const B = await extractAudioEnvelope(videoAsset, rate);
  const La = A.length;
  const Lb = B.length;
  assert(La > 0 && Lb > 0, "No reliable alignment found: an asset has no decodable audio.");

  const cc = crossCorrelate(A, B);
  const n = cc.length;
  const pa = prefixSums(A);
  const pb = prefixSums(B);
  const minOverlap = Math.max(1, Math.floor(rate * SYNC_MIN_OVERLAP_SEC));

  // Pearson correlation of the overlapping region at lag L (audio index i ↔
  // video index i+L), computed in O(1) from prefix sums + the FFT dot product.
  const nccAt = (L: number): number => {
    const iLo = Math.max(0, -L);
    const iHi = Math.min(La, Lb - L);
    const cnt = iHi - iLo;
    if (cnt < minOverlap) return -Infinity;
    const jLo = iLo + L;
    const jHi = iHi + L;
    const sumA = pa.sum[iHi] - pa.sum[iLo];
    const sumSqA = pa.sumSq[iHi] - pa.sumSq[iLo];
    const sumB = pb.sum[jHi] - pb.sum[jLo];
    const sumSqB = pb.sumSq[jHi] - pb.sumSq[jLo];
    const meanA = sumA / cnt;
    const meanB = sumB / cnt;
    const varA = sumSqA - cnt * meanA * meanA;
    const varB = sumSqB - cnt * meanB * meanB;
    if (varA <= 1e-9 || varB <= 1e-9) return -Infinity;
    const dot = cc[((L % n) + n) % n];
    const cov = dot - cnt * meanA * meanB;
    return cov / Math.sqrt(varA * varB);
  };

  let bestL = 0;
  let bestNcc = -Infinity;
  for (let L = -(La - 1); L <= Lb - 1; L++) {
    const v = nccAt(L);
    if (v > bestNcc) {
      bestNcc = v;
      bestL = L;
    }
  }
  assert(
    bestNcc > -Infinity,
    "No reliable alignment found: the clips don't overlap enough to align.",
  );
  assert(
    bestNcc >= SYNC_NO_MATCH_FLOOR,
    "No reliable alignment found: the audio tracks share too little common sound.",
  );

  // Parabolic interpolation around the peak for sub-bin precision.
  let delta = 0;
  const ym = nccAt(bestL - 1);
  const yp = nccAt(bestL + 1);
  if (Number.isFinite(ym) && Number.isFinite(yp)) {
    const denom = ym - 2 * bestNcc + yp;
    if (denom !== 0) delta = (0.5 * (ym - yp)) / denom;
    if (!Number.isFinite(delta) || Math.abs(delta) > 1) delta = 0;
  }

  return {
    offsetSeconds: (bestL + delta) / rate,
    confidence: Math.max(0, Math.min(1, bestNcc)),
  };
}
