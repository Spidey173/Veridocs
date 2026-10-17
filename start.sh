#!/usr/bin/env bash
set -e

echo "=========================================================="
echo "📑 Starting Veridocs (High-Performance Local AI Engine)..."
echo "=========================================================="

echo "1. Checking environment & starting FastAPI backend on http://127.0.0.1:8000..."
if [ ! -d ".venv" ]; then
    echo "Creating Python virtual environment in .venv..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip
    pip install -r backend/requirements.txt
else
    source .venv/bin/activate
fi

(cd backend && uvicorn main:app --host 127.0.0.1 --port 8000) &
BACKEND_PID=$!

echo "2. Starting Next.js frontend on http://localhost:3000..."
if [ ! -d "frontend/node_modules" ]; then
    echo "Installing frontend dependencies..."
    (cd frontend && npm install)
fi
(cd frontend && npm run dev) &
FRONTEND_PID=$!

cleanup() {
    echo ""
    echo "Stopping Veridocs services..."
    kill $BACKEND_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    exit 0
}

trap cleanup SIGINT SIGTERM EXIT

echo ""
echo "✨ Veridocs is running!"
echo "   - Web UI:  http://localhost:3000"
echo "   - API:     http://127.0.0.1:8000"
echo "   - Docs:    http://127.0.0.1:8000/docs"
echo ""
echo "Press Ctrl+C to stop all servers."
wait
