Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Get-Command py -ErrorAction SilentlyContinue) -and -not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python 3 is required but was not found."
}

if (Get-Command py -ErrorAction SilentlyContinue) {
    py -3 -m venv .venv
} else {
    python -m venv .venv
}

$Activate = Join-Path $Root ".venv\Scripts\Activate.ps1"
. $Activate

python -m pip install --upgrade pip
pip install -r requirements.txt

Write-Host ""
Write-Host "Starting Gezellig Dynamics Breach Review..."
Write-Host "Open http://127.0.0.1:8000"
python run.py
