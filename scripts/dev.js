#!/usr/bin/env node
const { spawn, execSync } = require('child_process');
const path = require('path');
const fs = require('fs');

const rootDir = path.resolve(__dirname, '..');
const backendDir = path.join(rootDir, 'backend');

console.log('==========================================================');
console.log('  🚀 Starting Veridocs (Frontend + Backend)');
console.log('  - Web App: http://localhost:3000');
console.log('  - API:     http://localhost:8000');
console.log('  - Docs:    http://localhost:8000/docs');
console.log('==========================================================\n');

const isWin = process.platform === 'win32';
const npmCmd = isWin ? 'npm.cmd' : 'npm';
const venvDir = path.join(rootDir, '.venv');
const venvPython = isWin
  ? path.join(venvDir, 'Scripts', 'python.exe')
  : path.join(venvDir, 'bin', 'python');
const venvPip = isWin
  ? path.join(venvDir, 'Scripts', 'pip.exe')
  : path.join(venvDir, 'bin', 'pip');

// 1. Ensure .venv exists and has requirements installed
if (!fs.existsSync(venvPython)) {
  console.log('Creating Python virtual environment in .venv...');
  let systemPython = 'python3';
  if (!isWin) {
    const candidates = ['python3.11', 'python3.12', 'python3'];
    for (const cand of candidates) {
      try {
        execSync(`command -v ${cand}`, { stdio: 'ignore' });
        systemPython = cand;
        break;
      } catch { }
    }
  } else {
    systemPython = 'python';
  }

  try {
    execSync(`${systemPython} -m venv "${venvDir}"`, { stdio: 'inherit', cwd: rootDir });
    console.log('Installing backend dependencies from requirements.txt...');
    execSync(`"${venvPip}" install --upgrade pip`, { stdio: 'inherit', cwd: rootDir });
    execSync(`"${venvPip}" install -r requirements.txt`, { stdio: 'inherit', cwd: rootDir });
  } catch (err) {
    console.error('Failed to set up Python virtual environment:', err);
    process.exit(1);
  }
}

// 2. Ensure .env exists
const envFile = path.join(rootDir, '.env');
const envExample = path.join(rootDir, '.env.example');
if (!fs.existsSync(envFile) && fs.existsSync(envExample)) {
  console.log('Creating .env from .env.example...');
  fs.copyFileSync(envExample, envFile);
}

// 3. Spawn FastAPI backend using .venv/bin/python
const backend = spawn(
  venvPython,
  ['-m', 'uvicorn', 'main:app', '--host', '0.0.0.0', '--port', '8000', '--reload', '--reload-dir', backendDir],
  {
    cwd: backendDir,
    stdio: 'inherit',
    env: {
      ...process.env,
      PYTHONPATH: [backendDir, process.env.PYTHONPATH].filter(Boolean).join(path.delimiter),
    },
  }
);

// 4. Spawn Next.js frontend
const frontend = spawn(npmCmd, ['run', 'dev:frontend'], {
  cwd: rootDir,
  stdio: 'inherit',
  env: {
    ...process.env,
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
  },
});

function cleanup() {
  console.log('\nShutting down Veridocs...');
  try {
    backend.kill('SIGINT');
  } catch { }
  try {
    frontend.kill('SIGINT');
  } catch { }
  process.exit(0);
}

process.on('SIGINT', cleanup);
process.on('SIGTERM', cleanup);
process.on('exit', cleanup);
