'use strict';

const { spawn, spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const CANDIDATES = process.platform === 'win32'
  ? [['py', ['-3']], ['python', []], ['python3', []]]
  : [['python3', []], ['python', []]];

function findPython() {
  const override = process.env.UNITY_SENTINEL_PYTHON;
  if (override) {
    const probe = spawnSync(override, ['--version'], { encoding: 'utf8' });
    if (probe.status === 0) {
      return { command: override, prefix: [] };
    }
  }
  for (const [command, prefix] of CANDIDATES) {
    const probe = spawnSync(command, [...prefix, '--version'], { encoding: 'utf8' });
    if (probe.status === 0) {
      return { command, prefix };
    }
  }
  return null;
}

function resolveToolkit(projectDir) {
  const local = path.join(projectDir, '.sentinel', 'toolkit');
  if (fs.existsSync(path.join(local, 'scripts', 'sentinel.py'))) {
    return local;
  }
  const packaged = path.resolve(__dirname, '..', '..');
  if (fs.existsSync(path.join(packaged, 'scripts', 'sentinel.py'))) {
    return packaged;
  }
  return null;
}

/**
 * Run the Python CLI, streaming output to the parent terminal.
 * @returns {Promise<number>} exit code of the Python process
 */
function runSentinel(projectDir, args) {
  const python = findPython();
  if (!python) {
    // eslint-disable-next-line no-console
    console.error(
      'error: Python 3.10+ was not found. Install Python or set UNITY_SENTINEL_PYTHON to its path.',
    );
    return Promise.resolve(3);
  }
  const toolkit = resolveToolkit(projectDir);
  if (!toolkit) {
    // eslint-disable-next-line no-console
    console.error('error: UNITY SENTINEL toolkit not found. Run `npx unity-sentinel init` first.');
    return Promise.resolve(3);
  }

  const script = path.join(toolkit, 'scripts', 'sentinel.py');
  const command = python.command;
  const argv = [...python.prefix, script, ...args];

  return new Promise((resolve) => {
    const child = spawn(command, argv, {
      stdio: 'inherit',
      cwd: projectDir,
      env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' },
    });
    child.on('error', (error) => {
      // eslint-disable-next-line no-console
      console.error(`error: failed to start Python: ${error.message}`);
      resolve(3);
    });
    child.on('close', (code, signal) => {
      if (signal) {
        resolve(3);
        return;
      }
      resolve(typeof code === 'number' ? code : 3);
    });
  });
}

module.exports = { findPython, resolveToolkit, runSentinel };
