# SMOKE.md — Smoke Test & Server Operations Runbook

> This document defines mandatory operational rules for any AI agent performing smoke tests, server operations, or release workflows on this project.
> Violations of these rules may cause **production outages** on live VPS infrastructure.

---

## 1. Golden Rules

1. **Plan before execute.** Any non-trivial operation (smoke test, deployment, server modification) MUST output a written plan and receive explicit user approval before execution begins. Never skip the plan.
2. **Production is sacred.** The VPS (`root@23.94.180.112`) runs live `sing-box` and `warp-svc` services. Direct testing on the host WILL disrupt production traffic. All testing must be isolated.
3. **Use the simplest tool.** If you can SSH directly, do not route through MCP intermediaries (e.g. Codex). If a single command answers the question, do not design a multi-step verification pipeline.
4. **Cite your sources.** Every factual claim (version numbers, service status, resource usage) must include: what you queried, when you queried it, and the raw result. Never state facts based on assumption or cached knowledge.

---

## 2. Smoke Test Procedure

Follow this exact sequence. Do not skip or reorder steps.

### Phase 1 — Local Verification (on Mac)

```
1. Create a temporary venv (outside the project tree)
2. pip install -e .
3. Run: automated-sing-box-generator --help
4. Run: automated-sing-box-generator doctor
5. Confirm: no import errors, no syntax errors, CLI layout correct
```

- This phase uses the local terminal directly. No SSH. No Codex.
- If local verification fails, stop. Do not proceed to remote testing.

### Phase 2 — Version Verification

```
1. Query PyPI JSON API:
   curl -s https://pypi.org/pypi/automated-sing-box-generator/json | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['info']['version'])"
2. Record: query timestamp, returned version, release status
3. Cross-check: compare PyPI version against pyproject.toml and GitHub Release tag
```

- Acceptable sources: PyPI JSON API, GitHub Releases API, `gh release list`
- Unacceptable sources: local pip cache, memory, assumption, "it should be"

### Phase 3 — Remote Docker Verification (via SSH)

```
1. ssh root@<VPS_IP> 'docker version'
2. ssh root@<VPS_IP> 'docker info'
3. ssh root@<VPS_IP> 'docker run --rm python:3.10-slim python --version'
```

- If all three succeed, Docker is alive. That's it. No additional health checks needed.
- Use direct SSH from local shell. Do not use Codex or other MCP intermediaries.

### Phase 4 — Isolated Container Test (via SSH + Docker)

```
1. ssh root@<VPS_IP> 'docker run -d --name test-env python:3.10-slim sleep 3600'
2. ssh root@<VPS_IP> 'docker exec test-env pip install automated-sing-box-generator==<VERSION>'
3. ssh root@<VPS_IP> 'docker exec test-env automated-sing-box-generator --help'
4. ssh root@<VPS_IP> 'docker exec test-env automated-sing-box-generator doctor'
5. ssh root@<VPS_IP> 'docker stop test-env && docker rm test-env'
```

- **NEVER** run `automated-sing-box-generator` commands directly on the VPS host.
- The container is disposable. Always clean up after testing.

---

## 3. Server Operation Rules

### Forbidden Actions (without explicit approval)

| Action | Reason |
|--------|--------|
| Running `automated-sing-box-generator` on VPS host | Will overwrite live sing-box config and restart services |
| Stopping/restarting `sing-box` or `warp-svc` | Production traffic disruption |
| Modifying `/etc/sing-box/` or systemd units on host | Config corruption risk |
| Running interactive TUI tools (btop, htop, top) via MCP | They consume resources while running; read and close immediately |
| `apt upgrade` or kernel updates without approval | Reboot risk on production server |

### Resource Monitoring

- The VPS is a **1-core CPU / 1GB RAM** machine. Be aware of resource constraints.
- If you start a monitoring process (btop, top, etc.), it will consume CPU while running. That's expected behavior, not a server alert. Read the output and terminate the process immediately.
- Do not report self-inflicted resource consumption as a server health issue.

### SSH Access

- Use local SSH directly: `ssh root@<VPS_IP> '<command>'`
- SSH key authentication is pre-configured; no password needed.
- Prefer one-shot commands (`ssh host 'cmd'`) over interactive sessions.

---

## 4. Release Workflow

```
1. Bump version in pyproject.toml
2. Create branch, commit, push, open PR
3. Merge PR to main
4. Create GitHub Release with matching tag (e.g. v0.3.16)
5. GitHub Actions (.github/workflows/publish.yml) automatically publishes to PyPI
6. Verify: gh run list --workflow=publish.yml --limit 1  →  status: completed / success
7. Verify: query PyPI JSON API to confirm new version is live
```

- The publish workflow is triggered by GitHub Release events, not by push to main.
- Do not manually upload to PyPI. The CI pipeline handles it.
- Always verify the pipeline completed successfully after creating a release.

---

## 5. PR & Git Conventions

- `main` is a protected branch. All changes go through PRs.
- Use conventional commit prefixes: `feat:`, `fix:`, `chore:`, `bump:`, `refactor:`, `docs:`
- Prefer merge commits (not squash) unless the branch has messy intermediate commits.
- Delete remote branches after merge.
- After merge, sync local: `git checkout main && git pull origin main`

---

## 6. Planning & Communication Rules

1. **Always plan first** for operations involving: server access, Docker, releases, config changes, or any destructive action.
2. **State your data sources** when presenting facts. Example:
   - ✅ "PyPI API queried at 11:40 UTC+8 returns version 0.3.15 as latest"
   - ❌ "The latest version is 0.3.15"
3. **Do not over-engineer** simple checks. If the user says "run X to verify", just run X. Do not add 5 extra verification steps.
4. **Use the most direct tool available.** Priority order: local terminal > direct SSH > MCP tools.
5. **When in doubt, ask.** Do not assume permissions. Do not assume the user wants you to proceed.
