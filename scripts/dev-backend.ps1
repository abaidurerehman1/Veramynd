# Start Veramynd backend API (FastAPI :8000)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $root "veramynd\backend")
python run.py @args
