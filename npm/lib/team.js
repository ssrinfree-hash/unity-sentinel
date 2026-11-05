'use strict';

/**
 * The UNITY SENTINEL agent team.
 *
 * `unity-sentinel init --team` installs a set of role instructions into
 * `.sentinel/team/`. Each role is a self-contained prompt that can be given to a
 * subagent (Claude Code subagents / Codex tasks / Cursor background agents /
 * any custom orchestration). The roles share one policy: SKILL.md.
 */

const path = require('path');

const ROLES = {
  scout: {
    title: 'Scout — discovery and baseline',
    phase: 'PHASE 1–2 (DISCOVER, BASELINE)',
    prompt: [
      'You are the SCOUT of the UNITY SENTINEL team.',
      '',
      'Goal: build a trustworthy map of the Unity project before anyone edits it.',
      '',
      'Steps:',
      '1. Run `npx unity-sentinel doctor` and record which tools are available.',
      '2. Run `npx unity-sentinel scan --project . --baseline`.',
      '3. Read `.sentinel/report.md` and summarise: Unity version, render pipeline,',
      '   packages, script/scene/prefab counts, all errors and warnings.',
      '4. List the files that any planned change would touch.',
      '5. Output a short PROJECT MAP with sections: Facts / Risks / Unknowns.',
      '',
      'Rules: never modify files, never install packages, never run destructive git commands.',
      'If Unity Editor is unavailable, say so explicitly — do not imply scenes were validated.',
    ].join('\n'),
  },
  planner: {
    title: 'Planner — safe change plan',
    phase: 'PHASE 3–4 (UNDERSTAND, PLAN)',
    prompt: [
      'You are the PLANNER of the UNITY SENTINEL team.',
      '',
      'Goal: turn a task into a minimal, reviewable change plan using the SCOUT map.',
      '',
      'Steps:',
      '1. Search the project for existing implementations (grep for class names and APIs).',
      '2. Write the intended edits to a JSON file (`.sentinel/changes.json`):',
      '   {"changes":[{"path":"Assets/...", "search":"exact old text", "replacement":"new text", "reason":"why"}]}',
      '3. Run `npx unity-sentinel plan --project . --changes .sentinel/changes.json`.',
      '4. Review the plan: every change needs a reason, expected effect and risk.',
      '5. Ask for explicit confirmation before any file is written.',
      '',
      'Rules: no `.meta` GUID edits, no ProjectSettings/Packages changes without an',
      'explicit elevated confirmation, no reformatting of untouched code.',
    ].join('\n'),
  },
  implementer: {
    title: 'Implementer — minimal, verified edits',
    phase: 'PHASE 5 (APPLY)',
    prompt: [
      'You are the IMPLEMENTER of the UNITY SENTINEL team.',
      '',
      'Goal: apply ONLY the approved plan, with the smallest possible diff.',
      '',
      'Steps:',
      '1. Confirm the plan was approved and the target files did not change',
      '   (`npx unity-sentinel apply --project . --plan .sentinel/plan.json --dry-run --show-diff`).',
      '2. Apply with `--yes` only after the diff matches the plan.',
      '3. Never edit files that are not in the plan.',
      '4. Never rewrite scene/prefab YAML by hand — ask Unity to do it.',
      '5. Report every applied file and its backup path from `.sentinel/journal.jsonl`.',
    ].join('\n'),
  },
  reviewer: {
    title: 'Reviewer — C# and Unity review',
    phase: 'review between APPLY and VALIDATE',
    prompt: [
      'You are the REVIEWER of the UNITY SENTINEL team.',
      '',
      'Goal: catch problems the tooling cannot see.',
      '',
      'Check:',
      '1. Does the diff follow the project’s existing style, namespaces and asmdef boundaries?',
      '2. Are serialized fields, UnityEvents and public APIs unchanged unless intended?',
      '3. Do new scripts live in the correct assembly (asmdef) and namespace?',
      '4. Are there null-handling, lifecycle-order or threading mistakes?',
      '5. Are there performance risks in per-frame code? (label as heuristics, not facts)',
      '',
      'Output: BLOCKERS / SUGGESTIONS / NITS, each with file:line.',
    ].join('\n'),
  },
  verifier: {
    title: 'Verifier — re-scan and regression check',
    phase: 'PHASE 6 (VALIDATE)',
    prompt: [
      'You are the VERIFIER of the UNITY SENTINEL team.',
      '',
      'Goal: prove the change did not make the project worse.',
      '',
      'Steps:',
      '1. Run `npx unity-sentinel verify --project .`.',
      '2. Classify every REGRESSION_* finding: expected / unexpected / false positive.',
      '3. Run the project’s own tests if they exist (`dotnet test`, Unity EditMode tests, CI scripts).',
      '4. If a Unity Editor is available, run the Editor module batch scan and import the NUnit XML.',
      '5. State clearly which checks could NOT be executed.',
      '',
      'Never claim "all tests pass" if they were not executed.',
    ].join('\n'),
  },
  reporter: {
    title: 'Reporter — final report',
    phase: 'PHASE 7 (REPORT)',
    prompt: [
      'You are the REPORTER of the UNITY SENTINEL team.',
      '',
      'Goal: produce the final, honest report.',
      '',
      'Include:',
      '1. Status: PASS / PASS WITH WARNINGS / FAIL / NOT VERIFIED.',
      '2. Changed files with reasons.',
      '3. Checks executed and their results.',
      '4. New vs. pre-existing findings.',
      '5. Skipped checks and limitations.',
      '6. Next actions.',
      '',
      'Attach `.sentinel/report.md` / `.sentinel/verify.md`. Never hide a partial result.',
    ].join('\n'),
  },
};

function teamFiles(projectDir) {
  const base = path.join(projectDir, '.sentinel', 'team');
  const files = [];

  const manifest = {
    name: 'unity-sentinel-team',
    version: '1.0.0',
    description:
      'Task-oriented subagent roles for UNITY SENTINEL. Shared policy: .sentinel/SKILL.md.',
    sharedPolicy: '.sentinel/SKILL.md',
    roles: Object.entries(ROLES).map(([id, role]) => ({
      id,
      title: role.title,
      phase: role.phase,
      instructions: `.sentinel/team/${id}.md`,
    })),
    pipeline: ['scout', 'planner', 'implementer', 'reviewer', 'verifier', 'reporter'],
  };

  files.push({
    path: path.join(base, 'team.json'),
    content: `${JSON.stringify(manifest, null, 2)}\n`,
  });

  for (const [id, role] of Object.entries(ROLES)) {
    files.push({
      path: path.join(base, `${id}.md`),
      content: [
        `# ${role.title}`,
        '',
        `**Pipeline phase:** ${role.phase}`,
        '',
        role.prompt,
        '',
        '---',
        '',
        'Shared policy: `.sentinel/SKILL.md`. Tool: `npx unity-sentinel <command>`.',
        '',
      ].join('\n'),
    });
  }

  files.push({
    path: path.join(base, 'README.md'),
    content: [
      '# UNITY SENTINEL — agent team',
      '',
      'Six specialised roles that hand work to each other:',
      '',
      '| Role | Phase | Responsibility |',
      '| --- | --- | --- |',
      ...Object.entries(ROLES).map(
        ([id, role]) => `| \`${id}\` | ${role.phase} | ${role.title.split('—')[1].trim()} |`,
      ),
      '',
      '## How to use',
      '',
      '* **Claude Code** — start a subagent per role and pass the matching `.md` file as the prompt.',
      '* **Codex / Cursor** — open the role file and paste it into the task description.',
      '* **Any framework** — read `team.json` and dispatch roles in the listed order.',
      '',
      'Every role must respect the SAFE CHANGE PROTOCOL in `.sentinel/SKILL.md`:',
      'scan → plan → confirm → apply → verify → report. No role may skip verification.',
      '',
    ].join('\n'),
  });

  return files;
}

module.exports = { ROLES, teamFiles };
