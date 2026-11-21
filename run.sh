#!/usr/bin/env bash
set -e

ROOT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$ROOT_DIR"

echo "=========================================================="
echo "  🚀 Starting Veridocs Workspace"
echo "  - Web App: http://localhost:3000"
echo "=========================================================="

# 1. Ensure frontend dependencies are installed
if [ ! -d "$ROOT_DIR/frontend/node_modules" ]; then
    echo "Installing frontend dependencies (first-time setup)..."
    (cd "$ROOT_DIR/frontend" && npm install --legacy-peer-deps)
fi

# 2. Check if user explicitly requested full backend mode (--full or --backend)
START_BACKEND=false
for arg in "$@"; do
    if [ "$arg" == "--full" ] || [ "$arg" == "--backend" ]; then
        START_BACKEND=true
        break
    fi
done

if [ "$START_BACKEND" = true ]; then
    echo "Full mode requested: checking Python backend..."
    if [ -f "$ROOT_DIR/.venv/bin/python" ]; then
        VENV_PYTHON="$ROOT_DIR/.venv/bin/python"
    else
        PYTHON_CMD="python3"
        command -v python3 >/dev/null 2>&1 || PYTHON_CMD="python"
        "$PYTHON_CMD" -m venv "$ROOT_DIR/.venv" || true
        VENV_PYTHON="$ROOT_DIR/.venv/bin/python"
        [ -f "$VENV_PYTHON" ] && "$VENV_PYTHON" -m pip install -r "$ROOT_DIR/backend/requirements.txt" || true
    fi

    if [ -f "$VENV_PYTHON" ]; then
        echo "Starting backend on http://localhost:8000..."
        (cd "$ROOT_DIR/backend" && "$VENV_PYTHON" -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload) &
        BACKEND_PID=$!
    fi
fi

# 3. Start Next.js frontend
echo "Launching Next.js frontend on http://localhost:3000..."
(cd "$ROOT_DIR/frontend" && npm run dev) &
FRONTEND_PID=$!

cleanup() {
    echo ""
    echo "Stopping Veridocs..."
    kill $FRONTEND_PID 2>/dev/null || true
    [ -n "$BACKEND_PID" ] && kill $BACKEND_PID 2>/dev/null || true
    exit 0
}

trap cleanup SIGINT SIGTERM EXIT

echo ""
echo "=========================================================="
echo "  🚀 Veridocs is running!"
echo "  Open in browser: http://localhost:3000"
echo "  Press Ctrl+C to stop."
echo "=========================================================="
echo ""

wait
