@echo off
if not exist "%~dp0stop-public.ps1" (
  echo [STOP] Missing stop-public.ps1. No process was changed.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-public.ps1"
if errorlevel 1 (
  echo [FAILED] Stop verification failed. See the message above.
  pause
  exit /b 1
)
pause
