$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    $pythonCommand = Get-Command python.exe -ErrorAction Stop
    & $pythonCommand.Source -m venv (Join-Path $PSScriptRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
}
& $venvPython -m pip install --disable-pip-version-check -r (Join-Path $PSScriptRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Could not install Python dependencies.' }
$copilotCommand = Join-Path $PSScriptRoot '.tools\node_modules\.bin\copilot.cmd'
if (-not (Test-Path -LiteralPath $copilotCommand)) {
    $npmCommand = Get-Command npm.cmd -ErrorAction Stop
    & $npmCommand.Source install --prefix (Join-Path $PSScriptRoot '.tools') --no-save --no-audit --no-fund @github/copilot
    if ($LASTEXITCODE -ne 0) { throw 'Could not install GitHub Copilot CLI. Requires Node.js 22+.' }
}
& $venvPython -m screen_solver.app --check
if ($LASTEXITCODE -ne 0) { throw 'Local checks failed.' }
Write-Host 'Setup complete. Run .\login.ps1 once, then double-click start.vbs.'
