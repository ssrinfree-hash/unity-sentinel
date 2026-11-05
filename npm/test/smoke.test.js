#!/usr/bin/env node
'use strict';

/**
 * Zero-dependency smoke test for the npm wrapper.
 *
 * Verifies that the installer writes the expected files, that it never escapes
 * the project directory, and that the Python proxy forwards arguments and exit
 * codes correctly. It runs against a temporary copy of a synthetic fixture.
 */

const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const { init } = require('../lib/install');
const { resolveSelection, listAgents } = require('../lib/agents');
const { findPython, resolveToolkit } = require('../lib/python');
const { teamFiles } = require('../lib/team');

let failures = 0;

function test(name, fn) {
  try {
    fn();
    console.log(`ok   ${name}`);
  } catch (error) {
    failures += 1;
    console.error(`FAIL ${name}`);
    console.error(`     ${error.message}`);
  }
}

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'sentinel-npm-'));
const project = path.join(tmp, 'UnityProject');
fs.cpSync(path.join(REPO_ROOT, 'tests', 'fixtures', 'valid_project'), project, { recursive: true });

test('lists the four supported agents', () => {
  assert.deepStrictEqual(listAgents().sort(), ['claude', 'codex', 'cursor', 'generic']);
});

test('resolves "all" and rejects unknown agents', () => {
  assert.strictEqual(resolveSelection(['all']).length, 4);
  assert.deepStrictEqual(resolveSelection(['claude,cursor']).sort(), ['claude', 'cursor']);
  assert.throws(() => resolveSelection(['nope']), /Unknown agent/);
});

test('init installs toolkit, skill and adapters', () => {
  const result = init(project, { agents: ['claude', 'codex', 'cursor', 'generic'], team: true, force: true });
  assert.ok(result.actions.length > 0);
  const expected = [
    '.sentinel/SKILL.md',
    '.sentinel/.gitignore',
    '.sentinel/toolkit/scripts/sentinel.py',
    '.sentinel/toolkit/core/paths.py',
    '.claude/skills/unity-sentinel/SKILL.md',
    '.claude/skills/unity-sentinel/INSTRUCTIONS.md',
    '.cursor/rules/unity-sentinel.mdc',
    '.sentinel/agents/codex/SKILL.md',
    '.sentinel/agents/codex/AGENTS.snippet.md',
    '.sentinel/agents/generic/instructions.md',
    '.sentinel/team/team.json',
    '.sentinel/team/scout.md',
    '.sentinel/team/reporter.md',
  ];
  for (const relative of expected) {
    assert.ok(fs.existsSync(path.join(project, relative)), `missing ${relative}`);
  }
});

test('cursor rule has valid MDC frontmatter', () => {
  const content = fs.readFileSync(path.join(project, '.cursor', 'rules', 'unity-sentinel.mdc'), 'utf8');
  assert.ok(content.startsWith('---\n'));
  assert.ok(content.includes('alwaysApply: false'));
  assert.ok(content.includes('globs:'));
});

test('team manifest lists six roles in pipeline order', () => {
  const manifest = JSON.parse(fs.readFileSync(path.join(project, '.sentinel', 'team', 'team.json'), 'utf8'));
  assert.deepStrictEqual(manifest.pipeline, ['scout', 'planner', 'implementer', 'reviewer', 'verifier', 'reporter']);
  assert.strictEqual(manifest.roles.length, 6);
  for (const role of manifest.roles) {
    assert.ok(fs.existsSync(path.join(project, role.instructions)), `missing ${role.instructions}`);
  }
});

test('team file generator refuses nothing outside the project', () => {
  const files = teamFiles(project);
  for (const file of files) {
    assert.ok(
      path.resolve(file.path).startsWith(path.resolve(project) + path.sep),
      `escaped project: ${file.path}`,
    );
  }
});

test('init is idempotent without --force (existing files are skipped)', () => {
  const result = init(project, { agents: ['claude'], force: false });
  const skipped = result.actions.filter((a) => a.reason === 'exists');
  assert.ok(skipped.length > 0, 'expected at least one skipped file');
});

test('python is discoverable', () => {
  const python = findPython();
  assert.ok(python, 'python not found');
  const probe = spawnSync(python.command, [...python.prefix, '--version'], { encoding: 'utf8' });
  assert.strictEqual(probe.status, 0);
});

test('toolkit resolves inside the project after init', () => {
  const toolkit = resolveToolkit(project);
  assert.strictEqual(toolkit, path.join(project, '.sentinel', 'toolkit'));
});

test('python proxy forwards arguments and exit codes', () => {
  const python = findPython();
  const script = path.join(project, '.sentinel', 'toolkit', 'scripts', 'sentinel.py');
  const run = (args) =>
    spawnSync(python.command, [...python.prefix, script, ...args], { cwd: project, encoding: 'utf8' });

  const ok = run(['version']);
  assert.strictEqual(ok.status, 0, ok.stderr);
  assert.ok(ok.stdout.includes('unity-sentinel'));

  const fail = run(['scan', '--project', 'tests-does-not-exist']);
  assert.strictEqual(fail.status, 3, 'missing project must be fatal');

  const broken = run(['scan', '--project', '.', '--out', path.join(tmp, 'out')]);
  assert.strictEqual(broken.status, 0, 'the valid fixture must scan cleanly');
});

test('wrapper CLI help exits 0', () => {
  const result = spawnSync(process.execPath, [path.join(REPO_ROOT, 'npm', 'bin', 'cli.js'), '--help'], {
    encoding: 'utf8',
  });
  assert.strictEqual(result.status, 0);
  assert.ok(result.stdout.includes('UNITY SENTINEL'));
});

test('wrapper CLI rejects unknown commands', () => {
  const result = spawnSync(process.execPath, [path.join(REPO_ROOT, 'npm', 'bin', 'cli.js'), 'nope'], {
    encoding: 'utf8',
  });
  assert.strictEqual(result.status, 3);
});

process.on('exit', () => {
  fs.rmSync(tmp, { recursive: true, force: true });
  if (failures > 0) {
    console.error(`\n${failures} test(s) failed`);
    process.exitCode = 1;
  } else {
    console.log('\nall npm wrapper tests passed');
  }
});
