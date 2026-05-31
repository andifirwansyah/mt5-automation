@echo off
setlocal

set "ROOT_DIR=%~dp0.."
cd /d "%ROOT_DIR%"

if not exist ".venv\Scripts\activate.bat" (
  echo [ERROR] Virtual environment not found at .venv\Scripts\activate.bat
  pause
  exit /b 1
)

call ".venv\Scripts\activate.bat"
python -m src.bot_worker

if errorlevel 1 (
  echo.
  echo [ERROR] Bot worker exited with error.
  pause
  exit /b 1
)

endlocal
