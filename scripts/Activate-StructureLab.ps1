$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ActivateScript = Join-Path $ProjectRoot ".venv_structurelab_pbd_rc\Scripts\Activate.ps1"

if (-not (Test-Path $ActivateScript)) {
    throw "Virtual environment not found at $ActivateScript"
}

Set-Location $ProjectRoot
. $ActivateScript
Write-Host "StructureLab_PBD_RC virtual environment active: $env:VIRTUAL_ENV"

