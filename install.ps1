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
