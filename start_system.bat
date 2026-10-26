@echo off
taskkill /F /IM node.exe >nul 2>&1
taskkill /F /IM python.exe >nul 2>&1
timeout /t 2 /nobreak >nul
cd /d "%~dp0"
start "Backend" cmd /k "call venv\Scripts\activate.bat && uvicorn server:app --port 8000"
timeout /t 3 /nobreak >nul
start "Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"
timeout /t 40 /nobreak >nul
start http://localhost:5173/