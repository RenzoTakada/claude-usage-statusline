param(
    [switch]$SkipSmokeTest
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ClaudeDir = Join-Path $HOME ".claude"
$ScriptsDir = Join-Path $ClaudeDir "scripts"
$SettingsFile = Join-Path $ClaudeDir "settings.json"
$TargetScript = Join-Path $ScriptsDir "claude_usage.py"
$CookiesDb = Join-Path $env:APPDATA "Claude\Cookies"

Write-Host "==> Claude Usage Status Line - Windows Installer"
Write-Host ""

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    $python = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $python) {
    throw "Python not found. Install Python 3 from python.org or the Microsoft Store."
}

$pythonCmd = $python.Source

try {
    & $pythonCmd -c "from cryptography.hazmat.primitives.ciphers import Cipher" 2>$null
} catch {
    Write-Host "==> Installing 'cryptography' Python package..."
    & $pythonCmd -m pip install --user --quiet cryptography
}

if (-not (Test-Path $CookiesDb)) {
    throw "Claude Desktop cookies database not found: $CookiesDb. Install Claude Desktop and log in first."
}

Write-Host "OK: Prerequisites OK"

New-Item -ItemType Directory -Force -Path $ScriptsDir | Out-Null
Copy-Item -Force (Join-Path $ScriptDir "claude_usage.py") $TargetScript
Write-Host "OK: Script installed at $TargetScript"

if (-not $SkipSmokeTest) {
    Write-Host "==> Testing script..."
    $output = & $pythonCmd $TargetScript 2>&1
    if ([string]::IsNullOrWhiteSpace($output)) {
        Write-Host ""
        Write-Warning "Script ran but returned no output. Make sure you are logged in to Claude Desktop."
        Write-Host "Debug manually: `$env:CLAUDE_USAGE_DEBUG=1; $pythonCmd $TargetScript"
    } else {
        Write-Host "OK: Script output: $output"
    }
}

Write-Host "==> Updating $SettingsFile ..."
New-Item -ItemType Directory -Force -Path $ClaudeDir | Out-Null

if (Test-Path $SettingsFile) {
    $settings = Get-Content $SettingsFile -Raw | ConvertFrom-Json
} else {
    $settings = [pscustomobject]@{}
}

$command = '"{0}" "{1}"' -f $pythonCmd, $TargetScript
$statusLine = [pscustomobject]@{
    type = "command"
    command = $command
    refreshInterval = 60
}

$settings | Add-Member -NotePropertyName "statusLine" -NotePropertyValue $statusLine -Force
$settings | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 $SettingsFile

Write-Host "OK: settings.json updated"
Write-Host ""
Write-Host "Installation complete!"
Write-Host ""
Write-Host "Restart Claude Code to see the status line:"
Write-Host "Session: 32% ###..... resets in 4h 8m  Weekly: 12% #....... resets in 5d 17h"
