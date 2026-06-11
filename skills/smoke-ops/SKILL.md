---
name: smoke-ops
description: Safe smoke-test, VPS operations, Docker verification, production server handling, and release/PyPI/GitHub validation for the Automated-sing-box-json-generator project. Use when Codex is asked to run or explain smoke tests, SSH to root@23.94.180.112, verify Docker or PyPI/GitHub releases, operate on the live VPS, deploy/uninstall/reconfigure sing-box/WARP, or perform any release workflow.
---

# Smoke Ops

Use this skill to prevent accidental disruption of the live VPS while testing or releasing this project.

## Required Workflow

1. Read `references/runbook.md` before taking action.
2. For smoke tests, server access, Docker checks, release work, config changes, or destructive actions, provide a written plan and wait for explicit user approval before executing.
3. Treat `root@23.94.180.112` as production infrastructure. Do not run `automated-sing-box-generator`, restart services, or modify `/etc/sing-box` directly on the host unless the user explicitly approves that exact operation.
4. Prefer isolated verification: local checks first, then remote Docker/container checks if needed.
5. When reporting factual claims such as versions, service status, or resource usage, include the command/source, query time, and raw result summary.

## Reference

The full mandatory procedure lives in `references/runbook.md`.
