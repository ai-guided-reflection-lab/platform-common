param([int]$ApiPort = 8101, [int]$GatewayPort = 8110, [switch]$Share)
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$workspaceRoot = Split-Path -Parent $projectRoot
$python = Join-Path $workspaceRoot '.venv\Scripts\python.exe'
$toolDir = Join-Path $workspaceRoot 'artifacts\lab-tools'
New-Item -ItemType Directory -Force -Path $toolDir | Out-Null
$env:ADAPTIVE_DATABASE_PATH = Join-Path $projectRoot 'data\adaptive.sqlite3'
$env:ADAPTIVE_LAB_MODE = 'true'
$env:ADAPTIVE_PLATFORM_ONLY = 'false'
$env:ADAPTIVE_LAB_API_URL = "http://127.0.0.1:$ApiPort"
$env:VITE_LAB_MODE = 'true'
Push-Location (Join-Path $projectRoot 'student-app')
try {
    & npm.cmd run build -- --configLoader runner
    if ($LASTEXITCODE -ne 0) { throw 'Student build failed.' }
} finally { Pop-Location }
$backend = Start-Process -FilePath $python -ArgumentList 'run_local.py','--port',"$ApiPort",'--no-reload' -WorkingDirectory (Join-Path $projectRoot 'backend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $toolDir 'backend.log') -RedirectStandardError (Join-Path $toolDir 'backend-error.log')
$gateway = Start-Process -FilePath $python -ArgumentList '-m','uvicorn','lab_gateway:app','--host','127.0.0.1','--port',"$GatewayPort" -WorkingDirectory (Join-Path $projectRoot 'backend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $toolDir 'gateway.log') -RedirectStandardError (Join-Path $toolDir 'gateway-error.log')
Write-Host "Student lab: http://127.0.0.1:$GatewayPort"
Write-Host "Processes: backend=$($backend.Id), gateway=$($gateway.Id)"
if ($Share) {
    $cloudflared = Join-Path $toolDir 'cloudflared.exe'
    if (-not (Test-Path $cloudflared)) {
        Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile $cloudflared
    }
    & $cloudflared tunnel --url "http://127.0.0.1:$GatewayPort"
}
