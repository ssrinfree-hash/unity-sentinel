# Installation

UNITY SENTINEL has two parts, installable independently:

| Part | What it is | Requirement |
| --- | --- | --- |
| Python toolkit | read-only analysis, planning, safe apply, reports | Python 3.10+ |
| npm wrapper | `npx` entry point that installs agents/skills and proxies commands | Node.js 18+ |
| Unity Editor module | optional Editor-side validation | Unity 2021.3 LTS or newer |

Nothing requires network access at runtime, and the Python toolkit has **zero
third-party dependencies**.

## 1. Quick start (npx, recommended)

```bash
cd /path/to/your/UnityProject
npx unity-sentinel init --agents all --team
```

Installs:

```
.sentinel/
  SKILL.md              shared agent policy
  toolkit/              self-contained Python toolkit (core/, scripts/, docs/, ...)
  team/                 six agent roles (scout … reporter)   [--team]
  .gitignore            ignores backups/journal/reports
.claude/skills/unity-sentinel/    [--agents claude]
.cursor/rules/unity-sentinel.mdc  [--agents cursor]
.sentinel/agents/codex/           [--agents codex]
.sentinel/agents/generic/         [--agents generic]
```

Then check the environment and run the first scan:

```bash
npx unity-sentinel doctor
npx unity-sentinel scan --project . --baseline
```

> `npx unity-sentinel` works once the package is published to npm. Until then use
> the GitHub form: `npx github:ssrinfree-hash/unity-sentinel init --agents all --team`.
> See [Publishing the npm package](#publishing-the-npm-package).

## 2. From a git clone

```bash
git clone https://github.com/ssrinfree-hash/unity-sentinel.git
cd unity-sentinel
python3 scripts/sentinel.py doctor
python3 scripts/sentinel.py scan --project /path/to/UnityProject
```

Add a shell alias if you like:

```bash
alias sentinel='python3 /path/to/unity-sentinel/scripts/sentinel.py'
```

## 3. As a Python package (optional)

```bash
python3 -m pip install .
unity-sentinel scan --project /path/to/UnityProject
```

The package exposes the `unity-sentinel` console script. The distribution name is
`unity-sentinel` and the top-level packages are `core` and `scripts`; if you
already have modules with these names, prefer the clone or npx installation.

## 4. Unity Editor module

Copy `unity/Editor` and `unity/Tests` into either:

* `Packages/unity-sentinel/` (local package, Editor-only assembly), or
* `Assets/UnitySentinel/`.

The assemblies declare `includePlatforms: ["Editor"]`, so no code is compiled
into player builds. Details: [`unity-integration.md`](unity-integration.md).

## 5. Verifying the installation

```bash
python3 -m unittest discover -s tests -t .        # 139 tests
python3 scripts/sentinel.py benchmark             # synthetic benchmark
node npm/test/smoke.test.js                       # npm wrapper smoke test
```

Expected: all tests pass; the benchmark reports the metrics documented in
[`benchmark.md`](benchmark.md).

## Publishing the npm package

The repository root is a valid npm package (`package.json`, `bin`). To publish:

```bash
npm login
npm publish --access public
```

The `files` field already restricts the tarball to the toolkit, adapters, docs and
metadata. If the name `unity-sentinel` is taken, rename it in `package.json` and
update the README commands.

## Requirements matrix

| Feature | Python 3.10+ | Node 18+ | Git | .NET | Unity Editor |
| --- | --- | --- | --- | --- | --- |
| scan / meta-check / references | required | – | recommended | – | – |
| plan / apply / revert | required | – | recommended | – | – |
| verify (regression) | required | – | recommended | – | – |
| C# compilation checks | – | – | – | optional | – |
| scene/prefab deep validation | – | – | – | – | required |
| Unity EditMode/PlayMode tests | – | – | – | – | required |
| `npx` installer | – | required | – | – | – |
