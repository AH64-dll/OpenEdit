# Downloaded-release/source installer for Windows x64. No system MLT install needed.
[CmdletBinding()]
param(
    [string]$InstallDir = $(if ($env:OPEN_EDIT_DIR) { $env:OPEN_EDIT_DIR } else { Join-Path $env:USERPROFILE 'OpenEdit' }),
    [switch]$NoProject,
    [switch]$SystemRuntime,
    [switch]$MediaOnly,
    [switch]$WithAgent,
    [switch]$Whisper
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
function Run-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Executable failed (exit $LASTEXITCODE). Installation is incomplete." }
}
$Source = $PSScriptRoot
if (-not $Source) { $Source = (Get-Location).Path }
$InstallDir = [IO.Path]::GetFullPath($InstallDir)
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
function Find-Python {
    foreach ($candidate in @('python', 'py')) {
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($command) {
            $extra = @(); if ($candidate -eq 'py') { $extra = @('-3') }
            & $command.Source @extra -c 'import sys; raise SystemExit(sys.version_info < (3,11,8))' 2>$null
            if ($LASTEXITCODE -eq 0) { return @{ Command=$command.Source; Arguments=$extra } }
        }
    }
    return $null
}
$Python = Find-Python
if (-not $Python) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw 'Install Python 3.12 from python.org, then rerun this installer. Windows App Installer/winget can also install it.'
    }
    Run-Checked winget @('install','--id','Python.Python.3.12','--exact','--scope','user','--accept-source-agreements','--accept-package-agreements','--silent')
    $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
    $Python = Find-Python
    if (-not $Python) { throw 'Restart PowerShell after installing Python, then rerun install.ps1.' }
}
if (-not (Test-Path (Join-Path $Source 'pyproject.toml')) -and -not (Test-Path (Join-Path $Source 'wheels'))) {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Download the release ZIP (no Git required) or install Git for a source install.' }
    $Source = Join-Path $InstallDir 'source'
    if (-not (Test-Path (Join-Path $Source '.git'))) { Run-Checked git @('clone','https://github.com/AH64-dll/OpenEdit.git',$Source) }
}
Run-Checked $Python.Command ($Python.Arguments + @('-I','-m','venv',(Join-Path $InstallDir '.venv')))
$Py = Join-Path $InstallDir '.venv\Scripts\python.exe'
$Bootstrap = @((Join-Path $Source 'scripts\bootstrap_runtime.py'),'--prefix',$InstallDir)
if ($SystemRuntime) { $Bootstrap += '--system-runtime' }
Run-Checked $Py $Bootstrap
Run-Checked $Py @('-I','-m','pip','install','--upgrade','pip')
if (Test-Path (Join-Path $Source 'wheels')) {
    $Wheels = @(Get-ChildItem (Join-Path $Source 'wheels\open_edit-*.whl'))
    if ($Wheels.Count -ne 1) { throw 'Expected one OpenEdit wheel in the release.' }
    $Package = $Wheels[0].FullName
} else { $Package = $Source }
$Extras = @(); if ($WithAgent) { $Extras += 'agent' }; if ($Whisper) { $Extras += 'whisper' }
if ($Extras.Count) { $Package += '[' + ($Extras -join ',') + ']' }
Run-Checked $Py @('-I','-m','pip','install','--upgrade','--force-reinstall','-c',(Join-Path $Source 'requirements\release-constraints.txt'),$Package)
Run-Checked $Py @('-I','-m','pip','check')
$Feature = 'graphics'; if ($MediaOnly) { $Feature = 'media' }
Run-Checked $Py @('-I','-m','open_edit.cli','setup',$Feature)
$Verify = @('-I',(Join-Path $Source 'scripts\verify_install.py'),'--output',(Join-Path $InstallDir 'install-report.json'))
if (-not $MediaOnly) { $Verify += '--graphics' }
Run-Checked $Py $Verify
$Launcher = '@echo off' + "`r`n" + '"%~dp0.venv\Scripts\python.exe" -I -m open_edit.cli serve %*' + "`r`n"
[IO.File]::WriteAllText((Join-Path $InstallDir 'OpenEdit.cmd'),$Launcher)
$Project = Join-Path $env:USERPROFILE 'OpenEditProjects\my-edit'
if ($env:OPEN_EDIT_STARTER_PROJECT) { $Project = $env:OPEN_EDIT_STARTER_PROJECT }
if (-not $NoProject) {
    New-Item -ItemType Directory -Force -Path $Project | Out-Null
    if (-not (Test-Path (Join-Path $Project '.open_edit\edit_graph.db'))) { Run-Checked $Py @('-I','-m','open_edit.cli','init',$Project) }
    foreach ($format in @('mcp','opencode','codex')) {
        $name = if ($format -eq 'codex') { 'codex.toml' } elseif ($format -eq 'mcp') { 'mcp.json' } else { 'opencode.json' }
        Run-Checked $Py @('-I','-m','open_edit.cli','mcp-config','--project',$Project,'--format',$format,'--output',(Join-Path $InstallDir $name))
    }
}
Write-Host "Verified OpenEdit installation: $InstallDir"
Write-Host "Start: $(Join-Path $InstallDir 'OpenEdit.cmd')"
if (-not $NoProject) {
    Write-Host "Agent settings: $(Join-Path $InstallDir 'mcp.json'), opencode.json or codex.toml"
} else {
    Write-Host 'Create a project, then run open_edit mcp-config --project PATH for agent settings.'
}
