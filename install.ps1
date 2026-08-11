#requires -Version 5.1
<#
Open Edit - one-command installer (Windows, PowerShell 5.1+)

Clones the Open Edit repository, creates a virtualenv, installs the MCP
server, verifies it, and (by default) creates a starter edit project.

Usage:
  .\install.ps1                      install to %USERPROFILE%\OpenEdit, starter project
  .\install.ps1 -InstallDir D:\OpenEdit
  .\install.ps1 -NoProject           skip the starter project
  .\install.ps1 -Help                show this help

Environment:
  OPEN_EDIT_DIR   install directory (used when -InstallDir is not given)

Notes:
  - No administrator rights required; everything stays under your user profile.
  - Re-running is safe: an existing clone is reused and updated.
  - If the script is blocked by the execution policy, run:
      powershell -ExecutionPolicy Bypass -File install.ps1
#>
[CmdletBinding()]
param(
    [string]$InstallDir = "",
    [switch]$NoProject,
    [switch]$Help
)

$ErrorActionPreference = "Stop"

$RepoUrl = "https://github.com/AH64-dll/OpenEdit.git"

function Write-Step([string]$Message) { Write-Host "==> $Message" -ForegroundColor Cyan }
function Write-Ok([string]$Message)   { Write-Host "==> $Message" -ForegroundColor Green }
function Write-WarnMsg([string]$Message) { Write-Host "warning: $Message" -ForegroundColor Yellow }
function Fail([string]$Message) {
    Write-Host "error: $Message" -ForegroundColor Red
    exit 1
}

if ($Help) {
    $helpText = @"
Open Edit installer - Windows (PowerShell 5.1+)

Usage:
  .\install.ps1                      install to %USERPROFILE%\OpenEdit, starter project
  .\install.ps1 -InstallDir D:\OpenEdit
  .\install.ps1 -NoProject           skip the starter project
  .\install.ps1 -Help                show this help

Parameters:
  -InstallDir <path>   install directory (default: %USERPROFILE%\OpenEdit)
  -NoProject           do not create the starter project (%USERPROFILE%\OpenEditProjects\my-talk)
  -Help                show this help

Environment:
  OPEN_EDIT_DIR        install directory (used when -InstallDir is not given)

Notes:
  - No administrator rights required; everything stays under your user profile.
  - Re-running is safe: an existing clone is reused and updated.
  - If the script is blocked by the execution policy, run:
      powershell -ExecutionPolicy Bypass -File install.ps1
"@
    Write-Host $helpText
    exit 0
}

# ---- Python detection (python, then the py launcher) -----------------------
$PyName = ""
$PyArgs = @()
$FoundOld = ""

function Invoke-Py([string]$Code) {
    if ($script:PyArgs.Count -gt 0) {
        & $script:PyName @script:PyArgs -c $Code
    } else {
        & $script:PyName -c $Code
    }
}

foreach ($cand in @("python", "py")) {
    if (-not (Get-Command $cand -ErrorAction SilentlyContinue)) { continue }
    if ($cand -eq "py") {
        $PyName = "py"; $PyArgs = @("-3")
    } else {
        $PyName = "python"; $PyArgs = @()
    }
    & $PyName @PyArgs -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
    if ($LASTEXITCODE -eq 0) {
        $PyVersion = & $PyName @PyArgs -c "import sys; print('.'.join(str(v) for v in sys.version_info[:3]))" 2>$null
        break
    }
    $PyVersion = & $PyName @PyArgs -c "import sys; print('.'.join(str(v) for v in sys.version_info[:3]))" 2>$null
    if ($PyVersion) { $FoundOld = "$cand ($PyVersion)" }
    $PyName = ""; $PyArgs = @()
}

if (-not $PyName) {
    if ($FoundOld) {
        Fail "Python 3.11+ is required but only $FoundOld was found. Install Python 3.11+ from https://www.python.org/downloads/ and re-run."
    }
    Fail "Python 3.11+ is required but neither 'python' nor the 'py' launcher was found on PATH. Install Python 3.11+ from https://www.python.org/downloads/ and re-run."
}
Write-Ok "Using Python $PyVersion ($PyName)"

# ---- Install directory -----------------------------------------------------
if ($InstallDir) {
    $InstallDir = $InstallDir.Trim()
}
if (-not $InstallDir) { $InstallDir = $env:OPEN_EDIT_DIR }
if (-not $InstallDir) { $InstallDir = Join-Path $env:USERPROFILE "OpenEdit" }
$InstallDir = [System.IO.Path]::GetFullPath($InstallDir)

# ---- Prerequisites ---------------------------------------------------------
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Fail "git is required but was not found on PATH. Install Git for Windows (https://git-scm.com/download/win) and re-run."
}

# ---- Clone (or reuse) ------------------------------------------------------
$gitDir = Join-Path $InstallDir ".git"
if (Test-Path -LiteralPath $gitDir) {
    Write-Step "Reusing existing clone at $InstallDir"
    $origin = & git -C $InstallDir remote get-url origin 2>$null
    if (($LASTEXITCODE -eq 0) -and ($origin -notmatch "OpenEdit")) {
        Fail "Directory $InstallDir is a git repository but its origin ($origin) does not look like Open Edit; remove it or pick another -InstallDir."
    }
    Write-Step "Updating existing clone (git pull --ff-only) ..."
    & git -C $InstallDir pull --ff-only 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-WarnMsg "could not fast-forward the existing clone; continuing with what is there"
    }
} elseif (Test-Path -LiteralPath $InstallDir) {
    $items = @(Get-ChildItem -LiteralPath $InstallDir -Force -ErrorAction SilentlyContinue)
    if ($items.Count -gt 0) {
        Fail "Install directory $InstallDir exists, is not empty, and is not a git clone. Remove it or choose another -InstallDir."
    }
    Write-Step "Cloning $RepoUrl into $InstallDir ..."
    & git clone $RepoUrl $InstallDir
    if ($LASTEXITCODE -ne 0) { Fail "git clone failed (exit $LASTEXITCODE). Check your network and git setup, then re-run." }
} else {
    Write-Step "Cloning $RepoUrl into $InstallDir ..."
    & git clone $RepoUrl $InstallDir
    if ($LASTEXITCODE -ne 0) { Fail "git clone failed (exit $LASTEXITCODE). Check your network and git setup, then re-run." }
}

if (-not (Test-Path -LiteralPath (Join-Path $InstallDir "pyproject.toml"))) {
    Fail "Clone at $InstallDir does not look like Open Edit (no pyproject.toml)."
}

# ---- Virtualenv + install --------------------------------------------------
$venvPy      = Join-Path $InstallDir ".venv\Scripts\python.exe"
$mcpBin      = Join-Path $InstallDir ".venv\Scripts\open-edit-mcp.exe"
$openEditBin = Join-Path $InstallDir ".venv\Scripts\open_edit.exe"

Set-Location $InstallDir
Write-Step "Creating virtualenv at $InstallDir\.venv ..."
& $PyName @PyArgs -m venv .venv
if ($LASTEXITCODE -ne 0) { Fail "Failed to create the virtualenv (exit $LASTEXITCODE)." }

Write-Step "Upgrading pip ..."
& $venvPy -m pip install -U pip
if ($LASTEXITCODE -ne 0) { Fail "pip upgrade failed (exit $LASTEXITCODE). Check your network connection, then re-run." }

Write-Step "Installing core package (.[mcp]) ..."
& $venvPy -m pip install -e ".[mcp]"
if ($LASTEXITCODE -ne 0) { Fail "pip install -e '.[mcp]' failed (exit $LASTEXITCODE). See the output above, then re-run." }

Write-Step "Installing optional extras (.[mcp,serve]) ..."
& $venvPy -m pip install -e ".[mcp,serve]"
if ($LASTEXITCODE -ne 0) { Write-WarnMsg ".[mcp,serve] (review UI) extras install failed; continuing without the review UI." }

Write-Step "Installing optional extras (.[mcp,whisper]) ..."
& $venvPy -m pip install -e ".[mcp,whisper]"
if ($LASTEXITCODE -ne 0) { Write-WarnMsg ".[mcp,whisper] (local transcription) extras install failed; continuing without whisper support." }

# ---- Render runtime: Node.js + HyperFrames engine --------------------------
$nodeBin = ""
$nodeCmd = Get-Command node -ErrorAction SilentlyContinue
if ($nodeCmd) {
    try {
        $nodeVer = (& node --version 2>$null)
        if ($nodeVer -match "^v(\d+)\.") {
            if ([int]$Matches[1] -ge 22) { $nodeBin = "node" }
            else { Write-WarnMsg "node $nodeVer is too old (>=22 required by hyperframes 0.7.65); attempting to install Node.js LTS" }
        }
    } catch { }
}
if (-not $nodeBin) {
    Write-Step "Node.js not found or too old. Attempting to install Node.js LTS ..."
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        try {
            & winget install --id OpenJS.NodeJS.LTS -e --accept-source-agreements --accept-package-agreements --silent 2>$null
            if ($LASTEXITCODE -eq 0) {
                $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
                $nodeCmd = Get-Command node -ErrorAction SilentlyContinue
                if ($nodeCmd) {
                    try {
                        $nodeVer = (& node --version 2>$null)
                        if (($nodeVer -match "^v(\d+)\.") -and ([int]$Matches[1] -ge 22)) { $nodeBin = "node" }
                    } catch { }
                }
            }
        } catch { Write-WarnMsg ("winget Node.js install failed: " + $_.Exception.Message) }
    }
}
if (-not $nodeBin) {
    Write-Step "Installing Node.js LTS into $InstallDir\.node (no admin needed) ..."
    $nodeDir = Join-Path $InstallDir ".node"
    $nodeRoot = Get-ChildItem -Path $nodeDir -Directory -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($nodeRoot -and (Test-Path -LiteralPath (Join-Path $nodeRoot.FullName "node.exe"))) {
        $nodeBin = Join-Path $nodeRoot.FullName "node.exe"
        $env:Path = $nodeRoot.FullName + ";" + $env:Path
        Write-Ok "Reusing previously installed Node.js at $nodeBin"
    } else {
        $nodeZip = Join-Path $env:TEMP "open-edit-node-lts.zip"
        try {
            [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
            Invoke-WebRequest -UseBasicParsing "https://nodejs.org/dist/latest-v22.x/node-v22.23.2-win-x64.zip" -OutFile $nodeZip -TimeoutSec 180
            Expand-Archive -Path $nodeZip -DestinationPath $nodeDir -Force
            $nodeRoot = Get-ChildItem -Path $nodeDir -Directory | Select-Object -First 1
            if ($nodeRoot -and (Test-Path -LiteralPath (Join-Path $nodeRoot.FullName "node.exe"))) {
                $nodeBin = Join-Path $nodeRoot.FullName "node.exe"
                $env:Path = $nodeRoot.FullName + ";" + $env:Path
            }
        } catch {
            Write-WarnMsg ("could not download Node.js: " + $_.Exception.Message)
        }
    }
}
if (-not $nodeBin) {
    Write-WarnMsg "Node.js is not available; skipping npm install. The HyperFrames overlay engine will be missing. Install Node.js LTS (22+) from https://nodejs.org/en/download and re-run."
} else {
    Write-Ok "Using Node.js: $nodeBin"
    Write-Step "Installing Node.js dependencies (npm install --no-audit --no-fund) ..."
    $npm = Join-Path (Split-Path $nodeBin -Parent) "npm.cmd"
    if (-not (Test-Path -LiteralPath $npm)) { $npm = "npm" }
    $npmExit = 1
    try {
        Push-Location $InstallDir
        & $npm install --no-audit --no-fund 2>$null
        $npmExit = $LASTEXITCODE
        Pop-Location
    } catch {
        Write-WarnMsg ("npm install failed: " + $_.Exception.Message)
        try { Pop-Location } catch { }
    }
    if ($npmExit -ne 0) {
        Write-WarnMsg "npm install failed (exit $npmExit). Retry with: cd $InstallDir; npm install --no-audit --no-fund"
    }
}
$hyperBin = Join-Path $InstallDir "node_modules\.bin\hyperframes.cmd"
$hyperReady = (Test-Path -LiteralPath $hyperBin)
if (-not $hyperReady) { $hyperReady = (Test-Path -LiteralPath (Join-Path $InstallDir "node_modules\.bin\hyperframes")) }
if ($hyperReady) {
    $hyperVer = ""
    try {
        $hyperVer = (& $hyperBin --version 2>$null)
    } catch { }
    if ($hyperVer -match "0\.7\.65") {
        Write-Ok "HyperFrames engine ready: $hyperBin ($hyperVer)"
    } else {
        Write-WarnMsg "hyperframes shim found at $hyperBin but its version check failed ($hyperVer); overlay rendering may be broken."
    }
} else {
    Write-WarnMsg "hyperframes binary not found; overlay rendering will fall back to npx (requires Node + network) or fail."
}

# ---- Verify the MCP server -------------------------------------------------
Write-Step "Verifying MCP server: $mcpBin --help ..."
& $mcpBin --help *> $null
if ($LASTEXITCODE -ne 0) {
    Write-WarnMsg "first verification attempt failed; showing output:"
    & $mcpBin --help
    Fail "MCP server verification failed ('open-edit-mcp --help' exited non-zero). Re-run the installer or inspect the pip output above."
}

# ---- Starter project -------------------------------------------------------
$projectDir = Join-Path $env:USERPROFILE "OpenEditProjects\my-talk"
$projectCreated = $false
if ($NoProject) {
    Write-Ok "Skipping starter project (-NoProject)."
} else {
    $ans = ""
    try { $ans = Read-Host "Create a starter project at $projectDir? [Y/n]" } catch { $ans = "" }
    if ($ans -match "^(n|no)$") {
        Write-Ok "Skipping starter project."
    } else {
        Write-Step "Creating starter project at $projectDir ..."
        New-Item -ItemType Directory -Force -Path $projectDir | Out-Null
        & $openEditBin init $projectDir
        if ($LASTEXITCODE -ne 0) { Fail "Failed to initialize the starter project at $projectDir (exit $LASTEXITCODE)." }
        $projectCreated = $true
    }
}

# ---- Render runtime: ffmpeg / melt / Chrome --------------------------------
$probes = @{}
$ffmpegCmd = Get-Command ffmpeg -ErrorAction SilentlyContinue
$probes["ffmpeg"] = if ($ffmpegCmd) { $ffmpegCmd.Source } else { "" }
$meltCmd = Get-Command melt -ErrorAction SilentlyContinue
$probes["melt"] = if ($meltCmd) { $meltCmd.Source } else { "" }

if (-not $probes["ffmpeg"]) {
    Write-Step "ffmpeg not found. Attempting install via winget (Gyan.FFmpeg) ..."
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        try {
            & winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements --silent 2>$null
            if ($LASTEXITCODE -eq 0) {
                $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
                $ffmpegCmd = Get-Command ffmpeg -ErrorAction SilentlyContinue
                if ($ffmpegCmd) { $probes["ffmpeg"] = $ffmpegCmd.Source }
            }
        } catch { Write-WarnMsg ("winget ffmpeg install failed: " + $_.Exception.Message) }
    }
    if (-not $probes["ffmpeg"]) {
        Write-WarnMsg "ffmpeg is still not on PATH. Install it manually from https://www.gyan.dev/ffmpeg/builds/ (or: winget install Gyan.FFmpeg) and re-run."
    }
}

if (-not $probes["melt"]) {
    Write-WarnMsg "melt (MLT) is not installed. Video-clip timelines require it for base-video rendering. There is currently no one-command melt install on Windows (no winget/chocolatey package; official builds are source-only on https://github.com/mltframework/mlt/releases). Options: build/install MLT yourself, use WSL with a Linux package (apt install melt), or use Open Edit for overlay/motion-graphics-only renders, which do not need melt."
}

$chromeFound = ""
$chromePaths = @(
    "C:\Program Files\Google\Chrome\Application\chrome.exe",
    "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    (Join-Path $env:LOCALAPPDATA "Google\Chrome\Application\chrome.exe"),
    "C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    (Join-Path $env:LOCALAPPDATA "Microsoft\Edge\Application\msedge.exe")
)
foreach ($p in $chromePaths) { if (Test-Path -LiteralPath $p) { $chromeFound = $p; break } }
if (-not $chromeFound) {
    $chCmd = Get-Command chrome, chrome.exe, msedge -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($chCmd) { $chromeFound = $chCmd.Source }
}

# ---- Runtime readiness summary ----------------------------------------------
Write-Host ""
Write-Host "Runtime readiness (render pipeline):" -ForegroundColor Cyan
$rows = @(
    @{ Name = "ffmpeg";      Status = if ($probes["ffmpeg"]) { "READY  " + $probes["ffmpeg"] } else { "MANUAL - https://www.gyan.dev/ffmpeg/builds/ (winget install Gyan.FFmpeg)" } },
    @{ Name = "melt (MLT)";  Status = if ($probes["melt"]) { "READY  " + $probes["melt"] } else { "MANUAL - no one-command Windows install; see warning above (WSL: apt install melt)" } },
    @{ Name = "node";        Status = if ($nodeBin) { "READY  " + $nodeBin } else { "MANUAL - https://nodejs.org/en/download (Node.js LTS)" } },
    @{ Name = "hyperframes"; Status = if ($hyperReady) { "READY  " + $hyperBin } else { "MANUAL - cd $InstallDir; npm install --no-audit --no-fund" } },
    @{ Name = "chrome";      Status = if ($chromeFound) { "READY  " + $chromeFound } else { "MANUAL - install Chrome, or: cd $InstallDir; npx @puppeteer/browsers install chrome" } }
)
foreach ($r in $rows) {
    if ($r.Status -like "READY*") {
        Write-Host ("  {0,-14} {1}" -f $r.Name, $r.Status) -ForegroundColor Green
    } else {
        Write-Host ("  {0,-14} {1}" -f $r.Name, $r.Status) -ForegroundColor Yellow
    }
}
Write-Host ""
Write-Host "Overlay/motion-graphics rendering uses the HyperFrames engine (HTML/CSS/JS) bundled in this repo - no extra install."

# ---- Summary ---------------------------------------------------------------
Write-Host ""
Write-Host "Open Edit installed successfully." -ForegroundColor Green
Write-Host ""
Write-Host ("  Clone directory : " + $InstallDir)
Write-Host ("  Virtualenv      : " + (Join-Path $InstallDir ".venv"))
Write-Host ("  MCP server      : " + $mcpBin)
if ($projectCreated) {
    Write-Host ("  Project         : " + $projectDir)
} else {
    Write-Host "  Project         : none (-NoProject)"
    Write-Host ("                   (create one later with: " + $openEditBin + " init <folder>)")
}
Write-Host ""
Write-Host ("Verification passed: " + $mcpBin + " --help")
Write-Host ""
Write-Host "Next steps:"
Write-Host ("  1. Register the MCP server with Cursor (or your agent host).")
Write-Host ("     Add to " + (Join-Path $env:USERPROFILE ".cursor\mcp.json") + ":")
Write-Host ""
if ($projectCreated) {
    $jsonCommand = $mcpBin.Replace("\", "\\")
    $jsonProject = $projectDir.Replace("\", "\\")
    Write-Host "     {"
    Write-Host "       `"mcpServers`": {"
    Write-Host "         `"open-edit`": {"
    Write-Host ("           `"command`": `"" + $jsonCommand + "`",")
    Write-Host ("           `"args`": [`"--project`", `"" + $jsonProject + "`"],")
    Write-Host "           `"env`": { `"OPEN_EDIT_RENDER_BACKEND`": `"cpu`" }"
    Write-Host "         }"
    Write-Host "       }"
    Write-Host "     }"
} else {
    Write-Host ("     Create a project later with: " + $openEditBin + " init <folder>")
    Write-Host "     then register it in mcp.json (see docs/MCP.md)."
}
Write-Host ""
Write-Host ("  2. Start the Review Studio:")
Write-Host ("       " + $openEditBin + " serve --review-only --port 8000")
Write-Host "     and open http://127.0.0.1:8000"
Write-Host ""
Write-Host "Done."
