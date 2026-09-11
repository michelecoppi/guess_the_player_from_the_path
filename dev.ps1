<#
.SYNOPSIS
    Runner per i comandi di sviluppo locale su Windows PowerShell.
.DESCRIPTION
    Inoltra i comandi a tools.dev senza richiedere l'installazione di GNU make.
.EXAMPLE
    .\dev.ps1 check-env
    .\dev.ps1 test
    .\dev.ps1 check
    .\dev.ps1 admin
    .\dev.ps1 webapp
#>

param(
    [Parameter(Position=0, ValueFromRemainingArguments=$true)]
    [string[]]$Arguments
)

$pythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $pythonExe) {
    Write-Error "Python non trovato nel PATH. Installa Python 3.11+ e aggiungilo al PATH."
    exit 1
}

& $pythonExe -m tools.dev @Arguments
exit $LASTEXITCODE
