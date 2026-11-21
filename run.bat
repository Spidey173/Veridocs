@echo off
echo ==========================================================
echo   Starting Veridocs (Frontend + Backend)
echo   - Web App: http://localhost:3000
echo   - Backend: http://localhost:8000
echo ==========================================================

REM Start FastAPI backend
start "Veridocs Backend" cmd /k "cd backend && python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"

REM Start Next.js frontend
set NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev:frontend
