#!/usr/bin/env bash
set -e

ROOT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$ROOT_DIR"

echo "=========================================================="
echo "  🚀 Starting Veridocs"
echo "  - Web App: http://localhost:3000"
echo "  - Backend: http://localhost:8000"
echo "=========================================================="

# Ensure frontend dependencies
if [ ! -d "$ROOT_DIR/node_modules" ]; then
    echo "Installing frontend dependencies..."
    npm install
fi

# Detect Python interpreter
PYTHON_CMD="python3"
if [ -f "$ROOT_DIR/.venv/bin/python" ]; then
    PYTHON_CMD="$ROOT_DIR/.venv/bin/python"
fi

# Start FastAPI backend
echo "Starting backend on http://localhost:8000..."
(
  export PYTHONPATH="$ROOT_DIR/.venv/lib/python3.11/site-packages:$ROOT_DIR/backend:$PYTHONPATH"
  cd "$ROOT_DIR/backend"
  $PYTHON_CMD -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
) &
BACKEND_PID=$!

# Start Next.js frontend
echo "Starting frontend on http://localhost:3000..."
(
  export NEXT_PUBLIC_API_URL="http://localhost:8000"
  npm run dev:frontend
) &
FRONTEND_PID=$!

cleanup() {
    echo ""
    echo "Stopping Veridocs..."
    kill $FRONTEND_PID 2>/dev/null || true
    kill $BACKEND_PID 2>/dev/null || true
    exit 0
}

trap cleanup INT TERM EXIT
wait
