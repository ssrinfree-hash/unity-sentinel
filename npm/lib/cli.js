'use strict';

const fs = require('fs');
const path = require('path');

const log = require('./log');
const { init } = require('./install');
const { listAgents, AGENTS } = require('./agents');
const { ROLES, teamFiles } = require('./team');
const { findPython, runSentinel } = require('./python');
const { looksLikeUnityProject } = require('./paths');
const { version: PACKAGE_VERSION } = require('../../package.json');

const PY_COMMANDS = new Set([
  'scan',
  'plan',
  'apply',
  'verify',
  'report',
  'meta-check',
  'references',
  'revert',
  'doctor',
  'benchmark',
  'version',
]);

const HELP = `
UNITY SENTINEL — Your AI Unity Engineering Guardian (v${PACKAGE_VERSION})

USAGE
  npx unity-sentinel <command> [options]

SETUP
  init                 Install the skill, the Python toolkit and agent adapters
  init --team          ...and the six-role agent team in .sentinel/team/
  team                 (Re)install only the agent team
  agents               Show supported agents and their integration status
  update               Refresh the local toolkit copy in .sentinel/toolkit

VERIFICATION (thin wrappers around the Python CLI)
  scan --project .             Read-only analysis, writes .sentinel/report.{json,md}
  meta-check --project .       Validate .meta files and GUID uniqueness
  references --project .       Look for unknown GUID references in assets
  plan --project . --changes changes.json
  apply --project . --plan .sentinel/plan.json [--dry-run] [--yes]
  verify --project .           Compare against the saved baseline
  report --input report.json   Re-render a Markdown report
  revert --project .           Undo changes recorded in the journal
  doctor                       Check Python/Git/dotnet/Unity availability
  benchmark                    Run the synthetic benchmark

INIT OPTIONS
  --project <dir>      Target project (default: current directory)
  --agents <list>      claude,codex,cursor,generic,all (default: claude)
  --team               Also install the agent team
  --force              Overwrite existing generated files
  --dry-run            Show what would be installed

EXAMPLES
  npx unity-sentinel init --agents all --team
  npx unity-sentinel scan --project .
  npx unity-sentinel scan --project . --baseline
  npx unity-sentinel plan --project . --changes .sentinel/changes.json
  npx unity-sentinel apply --project . --plan .sentinel/plan.json --dry-run --show-diff
  npx unity-sentinel verify --project .

Exit codes: 0 pass, 1 fail, 2 not verified, 3 fatal error.
`;

function parseOptions(argv) {
  const options = { agents: [], team: false, force: false, dryRun: false, project: null };
  const rest = [];
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    switch (arg) {
      case '--agents':
        options.agents.push(argv[++i] || '');
        break;
      case '--team':
        options.team = true;
        break;
      case '--force':
        options.force = true;
        break;
      case '--dry-run':
        options.dryRun = true;
        break;
      case '--project':
        options.project = argv[++i] || null;
        break;
      default:
        rest.push(arg);
    }
  }
  return { options, rest };
}

function resolveProject(options) {
  const projectDir = path.resolve(options.project || process.cwd());
  if (!fs.existsSync(projectDir) || !fs.statSync(projectDir).isDirectory()) {
    throw new Error(`Project directory does not exist: ${projectDir}`);
  }
  return projectDir;
}

function printActions(actions, projectDir) {
  const written = actions.filter((a) => a.written);
  const skipped = actions.filter((a) => !a.written && a.reason === 'exists');
  const dry = actions.filter((a) => a.reason === 'dry-run');

  for (const action of written) {
    log.ok(`${path.relative(projectDir, action.path)}`);
  }
  for (const action of skipped) {
    log.warn(`${path.relative(projectDir, action.path)} (exists, use --force to overwrite)`);
  }
  for (const action of dry) {
    log.info(`would write ${path.relative(projectDir, action.path)}`);
  }
  if (written.length === 0 && skipped.length === 0 && dry.length === 0) {
    log.warn('nothing to install');
  }
}

async function commandInit(argv) {
  const { options, rest } = parseOptions(argv);
  if (rest.length > 0) {
    log.warn(`ignoring unexpected arguments: ${rest.join(' ')}`);
  }
  const projectDir = resolveProject(options);
  if (!looksLikeUnityProject(projectDir)) {
    log.warn(
      `${projectDir} has no Assets/ folder — installing anyway, but scans will refuse to run.`,
    );
  }

  log.info(`installing UNITY SENTINEL into ${projectDir}`);
  const result = init(projectDir, options);
  printActions(result.actions, projectDir);

  log.plain('');
  log.info(`agents: ${result.agents.join(', ')}`);
  if (options.team) {
    log.info('agent team: .sentinel/team/ (scout, planner, implementer, reviewer, verifier, reporter)');
  }

  const python = findPython();
  if (!python) {
    log.warn('Python 3.10+ was not detected. Install Python or set UNITY_SENTINEL_PYTHON.');
  } else {
    log.ok(`python: ${python.command} ${python.prefix.join(' ')}`.trim());
  }

  log.plain('');
  log.plain('Next steps:');
  log.plain('  1. npx unity-sentinel doctor');
  log.plain('  2. npx unity-sentinel scan --project . --baseline');
  log.plain('  3. Read .sentinel/report.md and follow .sentinel/SKILL.md');
  return 0;
}

function commandTeam(argv) {
  const { options } = parseOptions(argv);
  const projectDir = resolveProject(options);
  const { installTeam } = require('./install');
  const actions = installTeam(projectDir, options);
  printActions(actions, projectDir);
  log.info('Team roles: ' + Object.keys(ROLES).join(', '));
  return 0;
}

function commandAgents() {
  log.plain('Supported agent adapters:');
  log.plain('');
  for (const [id, definition] of Object.entries(AGENTS)) {
    log.plain(`  ${id.padEnd(8)} ${definition.label.padEnd(16)} ${definition.status}`);
  }
  log.plain('');
  log.plain('Install with: npx unity-sentinel init --agents claude,codex,cursor,generic');
  return 0;
}

function commandUpdate(argv) {
  const { options } = parseOptions(argv);
  const projectDir = resolveProject(options);
  const { installToolkit } = require('./install');
  log.info('refreshing .sentinel/toolkit');
  const actions = installToolkit(projectDir, options);
  printActions(actions, projectDir);
  return 0;
}

function commandHelp() {
  log.plain(HELP);
  return 0;
}

async function commandProxy(command, argv) {
  // Only `--project` is interpreted here; every other flag is forwarded
  // verbatim so that Python-side options (--dry-run, --yes, --json, ...) work.
  let project = null;
  const forwarded = [];
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === '--project') {
      project = argv[i + 1] || null;
      i += 1;
      continue;
    }
    forwarded.push(argv[i]);
  }
  const projectDir = resolveProject({ project });
  return runSentinel(projectDir, [command, ...forwarded, '--project', projectDir]);
}

async function main(argv) {
  const [command, ...rest] = argv;
  if (!command || command === '--help' || command === '-h' || command === 'help') {
    return commandHelp();
  }
  if (command === '--version' || command === '-v') {
    log.plain(PACKAGE_VERSION);
    return 0;
  }

  switch (command) {
    case 'init':
      return commandInit(rest);
    case 'team':
      return commandTeam(rest);
    case 'agents':
      return commandAgents();
    case 'update':
      return commandUpdate(rest);
    default:
      break;
  }

  if (PY_COMMANDS.has(command)) {
    return commandProxy(command, rest);
  }

  log.error(`unknown command: ${command}`);
  log.plain(HELP);
  return 3;
}

module.exports = { main, parseOptions };
