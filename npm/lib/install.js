'use strict';

const fs = require('fs');
const path = require('path');

const { AGENTS, resolveSelection, readAsset } = require('./agents');
const { teamFiles } = require('./team');
const {
  PACKAGE_ROOT,
  TOOLKIT_DIRS,
  TOOLKIT_FILES,
  copyRecursive,
  ensureDir,
  isInsideProject,
  sentinelDir,
  toolkitDir,
  writeFile,
} = require('./paths');

const SENTINEL_GITIGNORE = [
  '# UNITY SENTINEL runtime artefacts',
  'backups/',
  'journal.jsonl',
  'plan.json',
  'report.json',
  'report.md',
  'verify.json',
  'verify.md',
  '',
  '# Keep the baseline under version control if you want reproducible regressions:',
  '# baseline.json',
  '',
].join('\n');

function installToolkit(projectDir, { dryRun = false, force = false } = {}) {
  const destination = toolkitDir(projectDir);
  const actions = [];

  if (!isInsideProject(projectDir, destination)) {
    throw new Error('Refusing to install outside the project directory.');
  }
  if (dryRun) {
    return [{ path: destination, written: false, reason: 'dry-run' }];
  }

  for (const dir of TOOLKIT_DIRS) {
    const source = path.join(PACKAGE_ROOT, dir);
    if (!fs.existsSync(source)) continue;
    copyRecursive(source, path.join(destination, dir));
    actions.push({ path: path.join(destination, dir), written: true });
  }
  for (const file of TOOLKIT_FILES) {
    const source = path.join(PACKAGE_ROOT, file);
    if (!fs.existsSync(source)) continue;
    ensureDir(destination);
    fs.copyFileSync(source, path.join(destination, file));
    actions.push({ path: path.join(destination, file), written: true });
  }
  return actions;
}

function installAgents(projectDir, selection, { dryRun = false, force = false } = {}) {
  const skillContent = readAsset('SKILL.md');
  const actions = [];
  for (const agent of selection) {
    const definition = AGENTS[agent];
    const instructions = [
      `# ${definition.label} adapter for UNITY SENTINEL`,
      '',
      `Integration status: ${definition.status}`,
      '',
      readAsset('agents', agent, 'instructions.md'),
    ].join('\n');

    for (const file of definition.files(projectDir, skillContent, instructions)) {
      if (dryRun) {
        actions.push({ path: file.path, written: false, reason: 'dry-run' });
        continue;
      }
      const result = writeFile(file.path, file.content, { force });
      actions.push({ path: file.path, ...result });
    }
  }
  return actions;
}

function installTeam(projectDir, { dryRun = false, force = false } = {}) {
  const actions = [];
  for (const file of teamFiles(projectDir)) {
    if (dryRun) {
      actions.push({ path: file.path, written: false, reason: 'dry-run' });
      continue;
    }
    const result = writeFile(file.path, file.content, { force });
    actions.push({ path: file.path, ...result });
  }
  return actions;
}

function installSentinelMeta(projectDir, { dryRun = false, force = false } = {}) {
  const actions = [];
  const gitignore = path.join(sentinelDir(projectDir), '.gitignore');
  if (dryRun) {
    actions.push({ path: gitignore, written: false, reason: 'dry-run' });
  } else {
    actions.push({ path: gitignore, ...writeFile(gitignore, SENTINEL_GITIGNORE, { force }) });
  }

  const skill = path.join(sentinelDir(projectDir), 'SKILL.md');
  if (dryRun) {
    actions.push({ path: skill, written: false, reason: 'dry-run' });
  } else {
    actions.push({ path: skill, ...writeFile(skill, readAsset('SKILL.md'), { force }) });
  }
  return actions;
}

function init(projectDir, options = {}) {
  const dryRun = Boolean(options.dryRun);
  const force = Boolean(options.force);
  const selection = resolveSelection(options.agents);

  const actions = [];
  actions.push(...installToolkit(projectDir, { dryRun, force }));
  actions.push(...installSentinelMeta(projectDir, { dryRun, force }));
  actions.push(...installAgents(projectDir, selection, { dryRun, force }));
  if (options.team) {
    actions.push(...installTeam(projectDir, { dryRun, force }));
  }
  return { actions, agents: selection, projectDir };
}

module.exports = { init, installToolkit, installAgents, installTeam, SENTINEL_GITIGNORE };
