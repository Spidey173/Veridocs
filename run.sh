#!/usr/bin/env bash
set -e

ROOT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$ROOT_DIR"

echo "=========================================================="
echo "  🚀 Starting Veridocs Engine"
echo "=========================================================="

# 1. Auto-generate backend/.env if missing
if [ ! -f "$ROOT_DIR/backend/.env" ]; then
    echo "Creating backend/.env from .env.example..."
    if [ -f "$ROOT_DIR/backend/.env.example" ]; then
        cp "$ROOT_DIR/backend/.env.example" "$ROOT_DIR/backend/.env"
    else
        touch "$ROOT_DIR/backend/.env"
    fi
    # Generate secure random AUTH_SECRET_KEY
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || python -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || openssl rand -hex 32 2>/dev/null || echo "veridocs_default_secret_key_32bytes_long")
    echo "AUTH_SECRET_KEY=$SECRET_KEY" >> "$ROOT_DIR/backend/.env"
fi

# 2. Cross-platform Python resolver (macOS/Linux: .venv/bin/python, Windows/GitBash: .venv/Scripts/python.exe)
if [ -f "$ROOT_DIR/.venv/bin/python" ]; then
    VENV_PYTHON="$ROOT_DIR/.venv/bin/python"
elif [ -f "$ROOT_DIR/.venv/Scripts/python.exe" ]; then
    VENV_PYTHON="$ROOT_DIR/.venv/Scripts/python.exe"
elif [ -f "$ROOT_DIR/venv/bin/python" ]; then
    VENV_PYTHON="$ROOT_DIR/venv/bin/python"
elif [ -f "$ROOT_DIR/venv/Scripts/python.exe" ]; then
    VENV_PYTHON="$ROOT_DIR/venv/Scripts/python.exe"
else
    echo "Setting up Python virtual environment..."
    PYTHON_CMD="python3"
    if ! command -v python3 >/dev/null 2>&1; then
        if command -v python >/dev/null 2>&1; then
            PYTHON_CMD="python"
        else
            echo "Error: Python is not installed or not in PATH."
            exit 1
        fi
    fi
    "$PYTHON_CMD" -m venv "$ROOT_DIR/.venv"
    if [ -f "$ROOT_DIR/.venv/bin/python" ]; then
        VENV_PYTHON="$ROOT_DIR/.venv/bin/python"
    else
        VENV_PYTHON="$ROOT_DIR/.venv/Scripts/python.exe"
    fi
    "$VENV_PYTHON" -m pip install --upgrade pip
    "$VENV_PYTHON" -m pip install -r "$ROOT_DIR/backend/requirements.txt"
fi

# 3. Ensure frontend dependencies exist
if [ ! -d "$ROOT_DIR/frontend/node_modules" ]; then
    echo "Installing frontend dependencies..."
    (cd "$ROOT_DIR/frontend" && npm install --legacy-peer-deps)
fi

# 4. Free up port 8000 and 3000 if previously occupied
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

# 5. Start Backend
echo "Starting FastAPI backend on http://localhost:8000..."
(cd "$ROOT_DIR/backend" && "$VENV_PYTHON" -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload --reload-exclude "uploads" --reload-exclude "uploads/*" --reload-exclude "uploads/**" --reload-exclude "*.npy" --reload-exclude "*.json") &
BACKEND_PID=$!

# 6. Start Frontend
echo "Starting Next.js frontend on http://localhost:3000..."
(cd "$ROOT_DIR/frontend" && npx next dev --turbopack) &
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
