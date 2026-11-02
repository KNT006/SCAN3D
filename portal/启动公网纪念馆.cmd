@echo off
if not exist "%~dp0start-public.ps1" (
  echo [STOP] Missing startup file: start-public.ps1
  echo This launcher did not change any running service.
  echo Please report this message. Do not disable security protection.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-public.ps1"
if errorlevel 1 (
  echo [FAILED] Public readiness was not confirmed. See the message above.
  pause
  exit /b 1
)
echo [OK] Website status and QR decode checks completed.
pause
