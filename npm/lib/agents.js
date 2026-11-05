'use strict';

/**
 * Agent integration targets.
 *
 * Only the Claude Code skills directory and the Cursor rules directory are
 * stable, documented conventions at the time of writing. Everything else is
 * installed under `.sentinel/agents/<agent>/` and must be wired up manually;
 * `docs/agent-compatibility.md` lists the exact status for each client.
 */

const path = require('path');
const fs = require('fs');

const AGENTS = {
  claude: {
    label: 'Claude Code',
    status: 'verified structure (.claude/skills)',
    /** @returns {{path: string, content: string}[]} */
    files(projectDir, skillContent, instructions) {
      const base = path.join(projectDir, '.claude', 'skills', 'unity-sentinel');
      return [
        { path: path.join(base, 'SKILL.md'), content: skillContent },
        { path: path.join(base, 'INSTRUCTIONS.md'), content: instructions },
      ];
    },
  },
  codex: {
    label: 'OpenAI Codex',
    status: 'manual wiring required (client versions differ)',
    files(projectDir, skillContent, instructions) {
      const base = path.join(projectDir, '.sentinel', 'agents', 'codex');
      return [
        { path: path.join(base, 'SKILL.md'), content: skillContent },
        { path: path.join(base, 'instructions.md'), content: instructions },
        {
          path: path.join(base, 'AGENTS.snippet.md'),
          content:
            '# UNITY SENTINEL\n\n' +
            'Before changing anything in this Unity project, read ' +
            '`.sentinel/agents/codex/SKILL.md` and follow its workflow.\n' +
            'Run `npx unity-sentinel scan --project .` before and `npx unity-sentinel verify --project .` after changes.\n',
        },
      ];
    },
  },
  cursor: {
    label: 'Cursor',
    status: 'verified structure (.cursor/rules)',
    files(projectDir, skillContent, instructions) {
      const base = path.join(projectDir, '.cursor', 'rules');
      const body = [
        '---',
        'description: UNITY SENTINEL — safe Unity change protocol',
        'globs: ["Assets/**/*.cs", "Assets/**/*.unity", "Assets/**/*.prefab"]',
        'alwaysApply: false',
        '---',
        '',
        instructions,
        '',
        '---',
        '',
        skillContent,
      ].join('\n');
      return [{ path: path.join(base, 'unity-sentinel.mdc'), content: body }];
    },
  },
  generic: {
    label: 'Generic agent',
    status: 'universal instructions',
    files(projectDir, skillContent, instructions) {
      const base = path.join(projectDir, '.sentinel', 'agents', 'generic');
      return [
        { path: path.join(base, 'SKILL.md'), content: skillContent },
        { path: path.join(base, 'instructions.md'), content: instructions },
      ];
    },
  },
};

function listAgents() {
  return Object.keys(AGENTS);
}

function resolveSelection(rawSelection) {
  if (!rawSelection || rawSelection.length === 0) return ['claude'];
  const seen = new Set();
  for (const item of rawSelection) {
    for (const name of String(item).split(',')) {
      const trimmed = name.trim();
      if (!trimmed) continue;
      if (trimmed === 'all') {
        for (const agent of listAgents()) seen.add(agent);
        continue;
      }
      if (!AGENTS[trimmed]) {
        throw new Error(
          `Unknown agent "${trimmed}". Available: ${listAgents().join(', ')}, all`,
        );
      }
      seen.add(trimmed);
    }
  }
  return [...seen];
}

function readAsset(...parts) {
  return fs.readFileSync(path.join(__dirname, '..', '..', ...parts), 'utf8');
}

module.exports = { AGENTS, listAgents, resolveSelection, readAsset };
