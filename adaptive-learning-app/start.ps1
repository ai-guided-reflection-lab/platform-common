param([switch]$UseConfiguredDatabase)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$workspaceRoot = Split-Path -Parent $projectRoot
$python = Join-Path $workspaceRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "Workspace Python environment not found at $python"
}

if (-not $UseConfiguredDatabase -and -not $env:ADAPTIVE_DATABASE_PATH) {
    $env:ADAPTIVE_DATABASE_PATH = Join-Path $projectRoot "data\adaptive.sqlite3"
}

$backend = Start-Process -FilePath $python -ArgumentList "-m", "uvicorn", "app.main:app", "--reload", "--port", "8100" -WorkingDirectory (Join-Path $projectRoot "backend") -WindowStyle Hidden -PassThru
$instructor = Start-Process -FilePath "npm.cmd" -ArgumentList "run", "dev", "--", "--configLoader", "runner" -WorkingDirectory (Join-Path $projectRoot "instructor-app") -WindowStyle Hidden -PassThru
$student = Start-Process -FilePath "npm.cmd" -ArgumentList "run", "dev", "--", "--configLoader", "runner" -WorkingDirectory (Join-Path $projectRoot "student-app") -WindowStyle Hidden -PassThru

Write-Host "Adaptive Learning is starting:"
Write-Host "  Instructor: http://127.0.0.1:5173"
Write-Host "  Student:    http://127.0.0.1:5174"
Write-Host "  API docs:   http://127.0.0.1:8100/docs"
Write-Host ""
Write-Host "Process IDs: backend=$($backend.Id), instructor=$($instructor.Id), student=$($student.Id)"
