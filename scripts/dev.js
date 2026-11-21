#!/usr/bin/env node
const { spawn } = require('child_process');
const path = require('path');

const rootDir = path.resolve(__dirname, '..');
const backendDir = path.join(rootDir, 'backend');

console.log('==========================================================');
console.log('  🚀 Starting Veridocs (Frontend + Backend)');
console.log('  - Web App: http://localhost:3000');
console.log('  - API:     http://localhost:8000');
console.log('==========================================================\n');

const isWin = process.platform === 'win32';
const npmCmd = isWin ? 'npm.cmd' : 'npm';
const pythonCmd = isWin ? 'python' : 'python3';

// 1. Spawn FastAPI backend
const backend = spawn(pythonCmd, ['-m', 'uvicorn', 'main:app', '--host', '0.0.0.0', '--port', '8000', '--reload'], {
  cwd: backendDir,
  stdio: 'inherit',
  shell: true,
  env: {
    ...process.env,
    PYTHONPATH: [
      path.join(rootDir, '.venv/lib/python3.11/site-packages'),
      backendDir,
    ].join(path.delimiter),
  },
});

// 2. Spawn Next.js frontend
const frontend = spawn(npmCmd, ['run', 'dev:frontend'], {
  cwd: rootDir,
  stdio: 'inherit',
  shell: true,
  env: {
    ...process.env,
    NEXT_PUBLIC_API_URL: 'http://localhost:8000',
  },
});

function cleanup() {
  console.log('\nShutting down Veridocs...');
  try {
    backend.kill('SIGINT');
  } catch {}
  try {
    frontend.kill('SIGINT');
  } catch {}
  process.exit(0);
}

process.on('SIGINT', cleanup);
process.on('SIGTERM', cleanup);
process.on('exit', cleanup);
