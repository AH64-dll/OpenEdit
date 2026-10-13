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
installed wheel's HTTP UI/health/static JavaScript. A temporary project with spaces
in its path is used; no user project is modified.

Local and native CI results are recorded below after completion. Model-provider
access and billed token/semantic accuracy measurements remain separate from media
pipeline verification. Optional ASR, every GPU/driver combination, macOS and ARM
release execution are not implied by these checks.
