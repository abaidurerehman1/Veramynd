# Start Veramynd frontend (Vite :5173)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $root "veramynd\frontend")
if (-not (Test-Path "node_modules")) {
  npm install
}
npm run dev @args
