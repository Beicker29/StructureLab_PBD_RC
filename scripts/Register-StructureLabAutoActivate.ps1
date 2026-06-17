[CmdletBinding()]
param(
    [switch]$Uninstall
)

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ProfilePath = $PROFILE.CurrentUserCurrentHost
$ProfileDirectory = Split-Path -Parent $ProfilePath
$StartMarker = "# >>> StructureLab_PBD_RC auto-activate >>>"
$EndMarker = "# <<< StructureLab_PBD_RC auto-activate <<<"

if (-not (Test-Path $ProfileDirectory)) {
    New-Item -ItemType Directory -Force -Path $ProfileDirectory | Out-Null
}

$ExistingContent = ""
if (Test-Path $ProfilePath) {
    $ExistingContent = Get-Content -Raw -Path $ProfilePath
}

$Pattern = "(?s)" + [regex]::Escape($StartMarker) + ".*?" + [regex]::Escape($EndMarker) + "\r?\n?"
$CleanContent = [regex]::Replace($ExistingContent, $Pattern, "")

if ($Uninstall) {
    Set-Content -Path $ProfilePath -Value $CleanContent -Encoding UTF8
    Write-Host "Removed StructureLab_PBD_RC auto-activation from $ProfilePath"
    exit 0
}

$EscapedProjectRoot = $ProjectRoot.Replace("'", "''")
$Block = @"
$StartMarker
`$env:STRUCTURELAB_PBD_RC_ROOT = '$EscapedProjectRoot'

function Invoke-StructureLabPbdRcAutoActivate {
    `$projectRoot = `$env:STRUCTURELAB_PBD_RC_ROOT
    if (-not `$projectRoot) { return }
    if (-not (Test-Path `$projectRoot)) { return }

    `$currentPath = (Get-Location).ProviderPath
    if (-not `$currentPath) { return }

    `$comparison = [System.StringComparison]::OrdinalIgnoreCase
    `$insideProject = `$currentPath.StartsWith(`$projectRoot, `$comparison)
    `$venvPath = Join-Path `$projectRoot ".venv_structurelab_pbd_rc"
    `$activateScript = Join-Path `$venvPath "Scripts\Activate.ps1"

    if (`$insideProject -and `$env:VIRTUAL_ENV -ne `$venvPath -and (Test-Path `$activateScript)) {
        . `$activateScript
    }
}

if (-not `$global:StructureLabPbdRcOriginalPrompt) {
    `$global:StructureLabPbdRcOriginalPrompt = `$function:prompt
}

function global:prompt {
    Invoke-StructureLabPbdRcAutoActivate
    if (`$global:StructureLabPbdRcOriginalPrompt) {
        & `$global:StructureLabPbdRcOriginalPrompt
    }
    else {
        "PS `$(`$executionContext.SessionState.Path.CurrentLocation)> "
    }
}

Invoke-StructureLabPbdRcAutoActivate
$EndMarker
"@

$NewContent = $CleanContent.TrimEnd() + [Environment]::NewLine + [Environment]::NewLine + $Block + [Environment]::NewLine
Set-Content -Path $ProfilePath -Value $NewContent -Encoding UTF8
Write-Host "Installed StructureLab_PBD_RC auto-activation in $ProfilePath"

