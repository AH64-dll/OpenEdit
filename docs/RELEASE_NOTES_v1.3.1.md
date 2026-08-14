# Open Edit v1.3.1

Open Edit is an AI-native video editor driven over the Model Context Protocol (MCP): agents inspect projects, apply edits, render, and QC through a local MCP stdio server. Everything is local-first — your media and edit history stay on your machine, with no cloud accounts or uploads. v1.3.1 makes the one-command installers provision the **entire render stack**, not just the Python MCP server, so a fresh download can actually render motion-graphics video out of the box.

## What's new

- **Installers provision the full render stack.** `install.sh` (Linux/macOS) and `install.ps1` (Windows) now go beyond clone + venv + pip: they detect (and, where possible, auto-install user-local — never with sudo) every runtime the render pipeline needs, then verify it.
- **Node.js + HyperFrames**: the installers detect Node ≥ 22 (the pinned hyperframes `0.7.65` engine requirement; auto-installing a user-local copy when missing), run `npm install`, and verify the pinned motion-graphics engine lands at `node_modules/.bin/hyperframes` and runs `--version`.
- **ffmpeg**: detected on PATH; when absent, Windows auto-installs via winget (`Gyan.FFmpeg`) and Linux prints exact package-manager commands — never a silent gap.
- **melt (MLT)**: checked on PATH on Linux (with apt/dnf/pacman/brew hints when missing). On Windows there is currently **no packaged melt** (no winget/chocolatey package; official builds are source-only), so the installer detects it and, if missing, ends with an explicit warning covering WSL (`apt install melt`) — overlay/motion-graphics-only renders work without melt.
- **Chrome/Chromium for puppeteer-core**: common browser paths are probed; if none is found the installer prints how to fetch one for HyperFrames, e.g. `npx @puppeteer/browsers install chrome`.
- **Runtime readiness summary**: every install ends with a clear status table naming which of ffmpeg / melt / node / hyperframes / chrome are ready vs. which need a manual step — no more post-install guessing. The `open-edit-mcp --help` verification still runs and must pass.
- **GPU (NVENC) encoder support**: final exports can encode on the GPU. With `OPEN_EDIT_RENDER_BACKEND=gpu` (the default), the renderer probes NVENC → AMF → QSV → VAAPI and falls back to `libx264` when no GPU encoder is available; set `OPEN_EDIT_RENDER_BACKEND=cpu` to always use software encoding. NVENC supports h264/hevc/av1 quality tiers and overrides (crf → cq, bitrate, preset, scale, codec).
- **Docs updates**: `INSTALL.md` render-stack prerequisites, `docs/MCP.md` render pipeline (native HyperFrames graphics → melt → ffmpeg composite/encode), and the agent install prompt in `docs/agent-install.md` now reflect the full render stack and GPU encode path.

## Proof point

The release's end-to-end validation: a **60-second HyperFrames logo intro** rendered through the pipeline at **1080p30 with GPU (NVENC) encode** — HyperFrames overlay capture, melt base track, ffmpeg composite and GPU encode, QC gate passed. That's the same path a fresh `install.sh` / `install.ps1` download now provisions automatically.

## Install

- Linux / macOS: `bash install.sh`
- Windows: `powershell -ExecutionPolicy Bypass -File install.ps1`
- One-command downloads: `curl -fsSL https://raw.githubusercontent.com/AH64-dll/OpenEdit/v1.3.1/install.sh | bash` · `irm https://raw.githubusercontent.com/AH64-dll/OpenEdit/v1.3.1/install.ps1 | iex`
- Full setup instructions: see `INSTALL.md` and the agent prompts in `docs/agent-install.md` / `docs/agent-configure.md`.
