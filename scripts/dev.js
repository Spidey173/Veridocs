#!/usr/bin/env node
const { spawn } = require('child_process');
const path = require('path');

const rootDir = path.resolve(__dirname, '..');
const isWin = process.platform === 'win32';

if (isWin) {
  // On Windows, trigger run.bat via cmd.exe
  const batPath = path.join(rootDir, 'run.bat');
  const child = spawn('cmd.exe', ['/c', batPath], {
    cwd: rootDir,
    stdio: 'inherit'
  });
  child.on('exit', (code) => process.exit(code || 0));
} else {
  // On macOS / Linux, run bash run.sh
  const shPath = path.join(rootDir, 'run.sh');
  const child = spawn('bash', [shPath], {
    cwd: rootDir,
    stdio: 'inherit'
  });
  child.on('exit', (code) => process.exit(code || 0));
}
