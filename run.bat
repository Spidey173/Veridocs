@echo off
setlocal enabledelayedexpansion

echo ==========================================================
echo   Veridocs - Enterprise Document Intelligence Engine
echo ==========================================================
echo.

cd /d "%~dp0"

:: 1. Check for Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    py --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo [ERROR] Python is not installed or not in PATH!
        echo Please install Python 3.10+ from https://www.python.org/downloads/
        pause
        exit /b 1
    ) else (
        set PYTHON_CMD=py
    )
) else (
    set PYTHON_CMD=python
)

:: 2. Check for Node.js
npm --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js / npm is not installed or not in PATH!
    echo Please install Node.js 18+ from https://nodejs.org/
    pause
    exit /b 1
)

:: 3. Auto-generate backend\.env if missing
if not exist "backend\.env" (
    echo [*] Creating backend\.env from .env.example...
    if exist "backend\.env.example" (
        copy "backend\.env.example" "backend\.env" >nul
    ) else (
        type nul > "backend\.env"
    )
    for /f "tokens=*" %%a in ('%PYTHON_CMD% -c "import secrets; print(secrets.token_hex(32))"') do set SECRET_KEY=%%a
    if defined SECRET_KEY (
        echo AUTH_SECRET_KEY=!SECRET_KEY!>> "backend\.env"
    )
)

:: 4. Setup Python Virtual Environment
if not exist ".venv\Scripts\python.exe" (
    echo [*] Setting up Python virtual environment (.venv)...
    %PYTHON_CMD% -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment!
        pause
        exit /b 1
    )
    echo [*] Installing backend dependencies...
    .venv\Scripts\python.exe -m pip install --upgrade pip
    .venv\Scripts\python.exe -m pip install -r backend\requirements.txt
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install backend dependencies!
        pause
        exit /b 1
    )
)

:: 5. Setup Frontend Dependencies
if not exist "frontend\node_modules" (
    echo [*] Installing frontend dependencies...
    cd frontend
    call npm install --legacy-peer-deps
    cd ..
)

echo.
echo ==========================================================
echo   Starting Veridocs Services...
echo   - Web App:      http://localhost:3000
echo   - API Backend:  http://localhost:8000
echo   - API Docs:     http://localhost:8000/docs
echo ==========================================================
echo.

:: 6. Launch Backend and Frontend in separate windows
start "Veridocs Backend API" cmd /k "cd /d "%~dp0\backend" && ..\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload --reload-exclude "uploads" --reload-exclude "uploads/*" --reload-exclude "*.npy" --reload-exclude "*.json""
start "Veridocs Frontend UI" cmd /k "cd /d "%~dp0\frontend" && npx next dev --turbopack"

echo Servers launched in background windows.
echo Close the terminal windows to stop the servers.
pause
