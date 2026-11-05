# Security policy

## Supported versions

| Version | Supported |
| --- | --- |
| 1.0.x | ✅ |

## Reporting a vulnerability

Please **do not** open a public issue for security problems.

* Preferred: GitHub Security Advisories — *Security → Report a vulnerability* on
  https://github.com/ssrinfree-hash/unity-sentinel
* Alternative: contact a maintainer privately and include a minimal reproduction.

Include:

1. affected version (`unity-sentinel version`);
2. the command and configuration used;
3. a description of the impact (data loss, path escape, secret leakage, …);
4. a minimal fixture or script if possible.

You can expect an acknowledgement within 7 days and a status update within 30
days. Please allow time for a fix before public disclosure.

## Threat model

UNITY SENTINEL is a **local** tool that reads a Unity project and can write to it
only inside a validated, journaled plan.

In scope:

* path traversal, absolute-path escape and symlink escape in `apply`;
* writing into generated/excluded directories;
* non-atomic writes or missing backups that could destroy user data;
* secret leakage into reports or logs;
* XML external-entity attacks in the Unity NUnit importer;
* dependency confusion through the npm/pip packaging.

Out of scope:

* running the tool on a project that is already malicious (arbitrary code in
  Unity assets is not executed by Sentinel, but Unity itself may execute it);
* security of third-party agents (Claude Code, Codex, Cursor) that drive the tool;
* denial of service against your own machine with pathological configurations.

## Built-in protections

* All writes funnel through `core/safe_operations.py`: containment check, symlink
  guard, excluded directories, protected paths, SHA-256 optimistic locking,
  exactly-one-match replacement, `O_EXCL` backups, atomic replace, journal.
* Revert refuses to touch files edited after Sentinel wrote them.
* Reports redact token-like strings and absolute user paths; credential-like files
  are never read for content.
* The Unity test-result importer disables DTD processing and external entity
  resolution.
* No network access, no telemetry, no hidden uploads.

## If you find a leaked secret in this repository

Open a private advisory; do not quote the secret in a public issue. Rotate the
credential immediately if it belongs to you.
