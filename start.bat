@echo off
:: start.bat - Start the SDS Retrieval Agent (FastAPI backend)
:: Run this from the project folder after setup.

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

echo.
echo  ==========================================
echo   SDS Retrieval Agent - Starting...
echo  ==========================================
echo.

:: Install Playwright browsers if not already done
echo [1/2] Checking Playwright browsers...
.venv\Scripts\python.exe -c "from playwright.sync_api import sync_playwright; p=sync_playwright().__enter__(); p.chromium.launch(headless=True); p.__exit__(None,None,None); print('OK')" 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Installing Playwright browsers ^(one-time^)...
    .venv\Scripts\playwright.exe install chromium
)

:: Start the FastAPI server
echo.
echo [2/2] Starting FastAPI server on http://127.0.0.1:8000
echo.
echo  Open your browser to: http://127.0.0.1:8000/app
echo  API docs at:          http://127.0.0.1:8000/docs
echo  Press Ctrl+C to stop.
echo.

.venv\Scripts\uvicorn.exe api:app --host 127.0.0.1 --port 8000 --reload
