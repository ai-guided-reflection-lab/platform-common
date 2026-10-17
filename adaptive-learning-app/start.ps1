param([switch]$UseConfiguredDatabase, [switch]$UseLocalSQLite, [int]$ApiPort = 0)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$workspaceRoot = Split-Path -Parent $projectRoot
$python = Join-Path $workspaceRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "Workspace Python environment not found at $python"
}

if ($UseConfiguredDatabase -and $UseLocalSQLite) {
    throw "Choose either the configured database or local SQLite."
}
if ($UseLocalSQLite) {
    $env:ADAPTIVE_DATABASE_PATH = Join-Path $projectRoot "data\adaptive.sqlite3"
} else {
    Remove-Item Env:ADAPTIVE_DATABASE_PATH -ErrorAction SilentlyContinue
}

if (-not $ApiPort) {
    $proxyFile = Join-Path $projectRoot "instructor-app\.env.local"
    if ((Test-Path $proxyFile) -and ((Get-Content -LiteralPath $proxyFile -Raw) -match 'ADAPTIVE_API_URL=http://127\.0\.0\.1:(\d+)')) { $ApiPort = [int]$Matches[1] }
    else { $ApiPort = 8100 }
}
foreach ($app in @("instructor-app", "student-app")) {
    $proxyFile = Join-Path $projectRoot "$app\.env.local"
    $proxyContent = if (Test-Path $proxyFile) { Get-Content -LiteralPath $proxyFile -Raw } else { "" }
    $proxyLine = "ADAPTIVE_API_URL=http://127.0.0.1:$ApiPort"
    if ($proxyContent -match '(?m)^ADAPTIVE_API_URL=.*$') { $proxyContent = $proxyContent -replace '(?m)^ADAPTIVE_API_URL=.*$', $proxyLine }
    else { $proxyContent += "`n$proxyLine`n" }
    Set-Content -LiteralPath $proxyFile -Value $proxyContent
}
$backend = Start-Process -FilePath $python -ArgumentList "run_local.py", "--port", "$ApiPort" -WorkingDirectory (Join-Path $projectRoot "backend") -WindowStyle Hidden -PassThru
$instructor = Start-Process -FilePath "npm.cmd" -ArgumentList "run", "dev", "--", "--configLoader", "runner" -WorkingDirectory (Join-Path $projectRoot "instructor-app") -WindowStyle Hidden -PassThru
$student = Start-Process -FilePath "npm.cmd" -ArgumentList "run", "dev", "--", "--configLoader", "runner" -WorkingDirectory (Join-Path $projectRoot "student-app") -WindowStyle Hidden -PassThru

Write-Host "Adaptive Learning is starting:"
Write-Host "  Instructor: http://127.0.0.1:5173"
Write-Host "  Student:    http://127.0.0.1:5174"
Write-Host "  API docs:   http://127.0.0.1:$ApiPort/docs"
Write-Host ""
Write-Host "Process IDs: backend=$($backend.Id), instructor=$($instructor.Id), student=$($student.Id)"
