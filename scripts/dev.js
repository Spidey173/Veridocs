#!/usr/bin/env node
const { spawn } = require('child_process');
const path = require('path');

const rootDir = path.resolve(__dirname, '..');
const frontendDir = path.join(rootDir, 'frontend');

console.log('==========================================================');
console.log('  🚀 Starting Veridocs Showcase Workspace');
console.log('  - Mode:    Instant Local Showcase (Zero Backend Needed)');
console.log('  - Web App: http://localhost:3000');
console.log('==========================================================\n');

const isWin = process.platform === 'win32';
const npmCmd = isWin ? 'npm.cmd' : 'npm';

const child = spawn(npmCmd, ['run', 'dev'], {
  cwd: frontendDir,
  stdio: 'inherit',
  shell: true,
});

child.on('exit', (code) => process.exit(code || 0));
