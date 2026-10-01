$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Virtual environment not found: $Python"
}

Push-Location $Root
try {
    & $Python -m ruff format --check .
    if ($LASTEXITCODE -ne 0) { throw "Ruff format check failed." }
    & $Python -m ruff check .
    if ($LASTEXITCODE -ne 0) { throw "Ruff check failed." }
    $env:QT_QPA_PLATFORM = "offscreen"
    & $Python -m pytest
    if ($LASTEXITCODE -ne 0) { throw "Tests failed." }

    & $Python -m PyInstaller --clean --noconfirm "packaging\qserialtool.spec"
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

    $Artifact = Join-Path $Root "dist\QSerialTool.exe"
    if (-not (Test-Path -LiteralPath $Artifact)) {
        throw "Expected artifact was not produced: $Artifact"
    }
    $Hash = (Get-FileHash -LiteralPath $Artifact -Algorithm SHA256).Hash.ToLowerInvariant()
    "$Hash  QSerialTool.exe" | Set-Content -LiteralPath "$Artifact.sha256" -Encoding ascii
    Write-Output "Built: $Artifact"
    Write-Output "SHA256: $Hash"
}
finally {
    Pop-Location
}