$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$copilotCommand = Join-Path $PSScriptRoot '.tools\node_modules\.bin\copilot.cmd'
if (-not (Test-Path -LiteralPath $copilotCommand)) {
    $copilotCommand = (Get-Command copilot.cmd -ErrorAction Stop).Source
}
& $copilotCommand login
if ($LASTEXITCODE -ne 0) { throw 'Copilot login failed.' }
