$ErrorActionPreference = 'Stop'
$pythonWindowless = Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonWindowless)) {
    $pythonWindowless = (Get-Command pythonw.exe -ErrorAction Stop).Source
}
$entryPoint = Join-Path $PSScriptRoot 'launch.pyw'
Start-Process -FilePath $pythonWindowless -ArgumentList ('"{0}"' -f $entryPoint) -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
