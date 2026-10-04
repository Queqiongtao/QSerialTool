@echo off
rem One-click Windows build entry: delegates to scripts\build.ps1 (gates + PyInstaller + SHA-256).
setlocal

set "SCRIPT=%~dp0scripts\build.ps1"
if not exist "%SCRIPT%" (
  echo [build] Missing script: %SCRIPT%
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" %*
set "CODE=%ERRORLEVEL%"

if "%CODE%"=="0" (
  echo [build] OK. Artifacts are in dist\.
) else (
  echo [build] FAILED with exit code %CODE%.
)

rem Double-clicked batch files close their console instantly, so pause only for that case.
echo %cmdcmdline% | find /i "%~f0" >nul
if not errorlevel 1 if not defined QST_NO_PAUSE pause

endlocal & exit /b %CODE%
