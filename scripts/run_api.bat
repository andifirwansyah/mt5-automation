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
uvicorn src.api.main:app --host 0.0.0.0 --port 8000

if errorlevel 1 (
  echo.
  echo [ERROR] API server exited with error.
  pause
  exit /b 1
)

endlocal
