@echo off
setlocal enabledelayedexpansion

echo ==========================================================
echo   Veridocs - Document Intelligence Workspace
echo   Web App: http://localhost:3000
echo ==========================================================
echo.

cd /d "%~dp0"

:: 1. Check for Node.js / npm
npm --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js is not installed or not in PATH!
    echo Please install Node.js 18+ from https://nodejs.org/
    pause
    exit /b 1
)

:: 2. Setup Frontend Dependencies
if not exist "frontend\node_modules" (
    echo [*] Installing frontend dependencies (first-time setup)...
    cd frontend
    call npm install --legacy-peer-deps
    cd ..
)

echo.
echo ==========================================================
echo   Launching Veridocs on http://localhost:3000
echo ==========================================================
echo.

cd frontend
call npm run dev
