#!/usr/bin/env bash
set -e

ROOT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$ROOT_DIR"

echo "=========================================================="
echo "  🚀 Starting Veridocs"
echo "  - Web App: http://localhost:3000"
echo "  - Backend: http://localhost:8000"
echo "  - Docs:    http://localhost:8000/docs"
echo "=========================================================="

# 1. Setup .env if missing
if [ ! -f "$ROOT_DIR/.env" ] && [ -f "$ROOT_DIR/.env.example" ]; then
    echo "Creating .env from .env.example..."
    cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
fi

# 2. Setup Python virtual environment if missing
if [ ! -d "$ROOT_DIR/.venv" ]; then
    echo "Creating Python virtual environment in .venv..."
    PYTHON_BIN="python3"
    if command -v python3.11 &>/dev/null; then
        PYTHON_BIN="python3.11"
    fi
    $PYTHON_BIN -m venv "$ROOT_DIR/.venv"
    "$ROOT_DIR/.venv/bin/pip" install --upgrade pip
    "$ROOT_DIR/.venv/bin/pip" install -r "$ROOT_DIR/requirements.txt"
fi

# 3. Ensure frontend dependencies
if [ ! -d "$ROOT_DIR/node_modules" ]; then
    echo "Installing frontend dependencies..."
    npm install
fi

# 4. Detect Python interpreter
PYTHON_EXEC="$ROOT_DIR/.venv/bin/python"
if [ ! -f "$PYTHON_EXEC" ]; then
    PYTHON_EXEC="python3"
fi

# 5. Start backend
echo "Starting backend on http://localhost:8000..."
(
  export PYTHONPATH="$ROOT_DIR/.venv/lib/python3.11/site-packages:$ROOT_DIR/backend:$PYTHONPATH"
  cd "$ROOT_DIR"
  "$PYTHON_EXEC" -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
) &
BACKEND_PID=$!

# 6. Start frontend
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
