#!/usr/bin/env bash
set -e

ROOT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$ROOT_DIR"

echo "Starting Veridocs..."

# Resolve Python from virtual environment
if [ -d "$ROOT_DIR/.venv" ]; then
    VENV_PYTHON="$ROOT_DIR/.venv/bin/python"
elif [ -d "$ROOT_DIR/venv" ]; then
    VENV_PYTHON="$ROOT_DIR/venv/bin/python"
else
    echo "Setting up Python virtual environment..."
    python3 -m venv "$ROOT_DIR/.venv"
    VENV_PYTHON="$ROOT_DIR/.venv/bin/python"
    "$VENV_PYTHON" -m pip install --upgrade pip
    "$VENV_PYTHON" -m pip install -r "$ROOT_DIR/backend/requirements.txt"
fi

# Ensure frontend dependencies exist
if [ ! -d "$ROOT_DIR/frontend/node_modules" ]; then
    echo "Installing frontend dependencies..."
    (cd "$ROOT_DIR/frontend" && npm install --legacy-peer-deps)
fi

# Free up port 8000 and 3000 if previously occupied
if command -v lsof >/dev/null 2>&1; then
    OLD_BACKEND=$(lsof -ti :8000 2>/dev/null || true)
    if [ -n "$OLD_BACKEND" ]; then
        echo "Clearing existing process on port 8000 (PID: $OLD_BACKEND)..."
        kill -9 $OLD_BACKEND 2>/dev/null || true
    fi
    OLD_FRONTEND=$(lsof -ti :3000 2>/dev/null || true)
    if [ -n "$OLD_FRONTEND" ]; then
        echo "Clearing existing process on port 3000 (PID: $OLD_FRONTEND)..."
        kill -9 $OLD_FRONTEND 2>/dev/null || true
    fi
fi

# Start Backend
echo "Starting FastAPI backend on http://localhost:8000..."
(cd "$ROOT_DIR/backend" && "$VENV_PYTHON" -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload) &
BACKEND_PID=$!

# Start Frontend
echo "Starting Next.js frontend on http://localhost:3000..."
(cd "$ROOT_DIR/frontend" && npm run dev) &
FRONTEND_PID=$!

cleanup() {
    echo ""
    echo "Stopping Veridocs servers..."
    kill $BACKEND_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    wait $BACKEND_PID 2>/dev/null || true
    wait $FRONTEND_PID 2>/dev/null || true
    exit 0
}

trap cleanup SIGINT SIGTERM EXIT

echo ""
echo "=========================================================="
echo "  🚀 Veridocs is running!"
echo "  - Web App:      http://localhost:3000"
echo "  - API Backend:  http://localhost:8000"
echo "  - API Docs:     http://localhost:8000/docs"
echo "  Press Ctrl+C to stop all servers."
echo "=========================================================="
echo ""

wait
