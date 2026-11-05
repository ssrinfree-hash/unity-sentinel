'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');

const PACKAGE_ROOT = path.resolve(__dirname, '..', '..');
const TOOLKIT_DIRS = ['core', 'scripts', 'config', 'agents', 'benchmark', 'docs'];
const TOOLKIT_FILES = ['SKILL.md', 'README.md', 'LICENSE', 'CHANGELOG.md'];

function packageRoot() {
  return PACKAGE_ROOT;
}

function sentinelDir(projectDir) {
  return path.join(projectDir, '.sentinel');
}

function toolkitDir(projectDir) {
  return path.join(sentinelDir(projectDir), 'toolkit');
}

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function copyRecursive(source, destination) {
  const stat = fs.statSync(source);
  if (stat.isDirectory()) {
    ensureDir(destination);
    for (const entry of fs.readdirSync(source)) {
      if (entry === '__pycache__' || entry === 'node_modules' || entry === '.git') continue;
      copyRecursive(path.join(source, entry), path.join(destination, entry));
    }
    return;
  }
  ensureDir(path.dirname(destination));
  fs.copyFileSync(source, destination);
}

function writeFile(destination, content, { force = false } = {}) {
  if (!force && fs.existsSync(destination)) {
    return { written: false, reason: 'exists' };
  }
  ensureDir(path.dirname(destination));
  fs.writeFileSync(destination, content, 'utf8');
  return { written: true };
}

function looksLikeUnityProject(dir) {
  try {
    return fs.statSync(path.join(dir, 'Assets')).isDirectory();
  } catch {
    return false;
  }
}

function isInsideProject(projectDir, target) {
  const relative = path.relative(projectDir, target);
  return relative === '' || (!relative.startsWith('..') && !path.isAbsolute(relative));
}

module.exports = {
  PACKAGE_ROOT,
  TOOLKIT_DIRS,
  TOOLKIT_FILES,
  packageRoot,
  sentinelDir,
  toolkitDir,
  ensureDir,
  copyRecursive,
  writeFile,
  looksLikeUnityProject,
  isInsideProject,
  homedir: os.homedir,
};
