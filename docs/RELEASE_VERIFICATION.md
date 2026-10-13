# Release verification

The release path provisions pinned Node 24.21.0 and official Shotcut 26.9.27
media runtimes (MLT 7.41), using publisher SHA-256 checksums. Both upstream archive
layouts were inspected; Windows includes melt.exe, ffmpeg.exe, ffprobe.exe and
matching MLT/Qt plugin directories. The Linux wrapper's MLT version was executed.
Native platform execution is required before a Windows readiness claim.

The smoke verifier connects via the actual generated stdio configuration, imports
real media, commits two clips, a centered dissolve, separate audio and an animated
transparent overlay. It renders proxy and final files, checks red/blended/blue
background pixels and two positions of the moving overlay, verifies media timing
and complete decoding, reopens through a second MCP session and checks the
installed wheel's HTTP UI/health/static JavaScript. It also exports through the
UI's real API from an immutable revision, checks the finished video and downloads
the exact verified file. A temporary project with spaces in its path is used;
no user project is modified.

## Recorded results · 13 October 2026

- Final clean regression run: **1,793 passed**, 11 browser tests excluded from
  that run, 190.47 seconds. Browser checks run independently in acceptance CI.
- [Python 3.11/3.12/3.13 CI](https://github.com/AH64-dll/OpenEdit/actions/runs/38358428270):
  all three jobs passed, including wheel builds and installed-package checks.
- [Graphics and browser acceptance](https://github.com/AH64-dll/OpenEdit/actions/runs/38357080015):
  Windows, Linux and macOS compiler/graphics checks and the Linux editing/browser,
  tracking, media, preview/export and optional-renderer workflow passed.
- [Native Linux download check](https://github.com/AH64-dll/OpenEdit/actions/runs/38351992864):
  the Ubuntu 24.04 package job passed, producing its download ZIP and actual
  media verification artifacts. The Windows run was superseded while adding
  bounded verification and setup-stage diagnostics; it is not Windows proof.
- Local Linux x64: a noneditable wheel installed from the extracted download
  into a path with spaces. All four core doctor capabilities were available.
  The 1.6-second editing/export smoke completed in 9.526 seconds; proxy rendering
  took 4.527 seconds and final rendering 2.216 seconds on this machine. Its
  pixel/timing/decode, reopen and installed UI checks all passed.
- Default starter setup generated standard MCP JSON, OpenCode JSON and Codex
  TOML. Rerunning setup preserved the starter database's SHA-256 and retained
  an explicitly selected local Chromium. OpenCode 1.19.0's real `mcp list`
  reported the generated installed-wheel server **connected**.
- Both download ZIPs and the source distribution were rebuilt and inspected.
  ZIP checksums, required wheel/installer/runtime/constraint files, and bundled
  connection and license documentation were verified. The revised guide was
  checked in Chromium at desktop and mobile widths, with no page overflow.

Both native package jobs passed in the
[Windows/Linux release workflow](https://github.com/AH64-dll/OpenEdit/actions/runs/38359495384),
including actual import, MCP edits, transition and animation pixels, synchronized
audio/video, complete decoding, reopening and the installed UI's immutable
export/download workflow. The final native run completed in 2 minutes 22 seconds.
This verification
found and fixed two Windows defects: retained output handles could prevent worker
completion, and custom/fractional render profiles created invalid cache paths.
Regression coverage now checks open output handles and distinct portable cache
keys. MLT runs in batch mode with closed input, and Windows logs use bounded
file capture.

The additional UI export/download check also passed locally in 17.405 seconds.
The native verifier handles Windows temporary-folder aliases and captures UI
logs in files, preventing undrained test pipes from blocking HTTP responses.
Inspect retained verification JSON and rendered MP4; archive creation alone is
not Windows proof.

## Limits

Model-provider access and billed token/semantic accuracy measurements remain
separate from media pipeline verification. The OpenCode connection above is an
actual host connection, not a successful live-model editing session. Provider
requests in this cloud session were blocked by destination policy. Optional ASR,
every GPU/driver combination, macOS and ARM release installation are not implied
by these checks. Windows release CI uses Windows Server 2025; arbitrary managed
Windows desktop policies are not covered. First installation requires Internet
access to package/runtime/browser publishers; the ZIP is not an offline bundle.
