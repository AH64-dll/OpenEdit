# Runtime licenses and provenance

The Python package includes OpenEdit's MIT source, vendored Diffusion MPL-2.0
source with its NOTICE/provenance files, and OpenEdit Sans under OFL-1.1. The wheel
ships the corresponding source and license files. No Remotion binary is bundled
on the default path; optional use retains its separate licensing terms.

The installers download the original, unmodified upstream runtime archives into
the user's installation. They are not redistributed inside OpenEdit's download
ZIPs. Their upstream notices remain with the extracted runtimes:

- Node.js 24.21.0: official nodejs.org distribution; MIT and bundled dependency
  notices in its LICENSE file. Checksums come from the official SHASUMS256.txt.
- Shotcut 26.9.27: official mltframework/shotcut GitHub release. Its distribution
  supplies MLT 7.41 and FFmpeg, with COPYING.txt and third-party notices. Shotcut
  is GPL-3.0; MLT and FFmpeg component licenses depend on enabled modules.
  Consult those supplied notices when redistributing any installed runtime.
- Corresponding upstream source: https://github.com/mltframework/shotcut/releases/tag/v26.9.27
  (includes shotcut-src-26.9.27.txz), https://github.com/mltframework/mlt and
  https://ffmpeg.org/download.html. Distribution build scripts/dependency versions
  are maintained by the Shotcut publisher in its release/build repositories.

Runtime download hashes are pinned in scripts/runtime-downloads.json and checked
before extraction. Playwright Chromium and npm workers use their upstream
installers and the shipped lockfiles, retaining dependency licenses. Python
packages retain their own license metadata. Review upstream licensing before
making a different self-contained binary distribution.
