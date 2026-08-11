# Project Plan: Direct (none) WARP Mode Addition

## Architecture Overview
The CLI tool `automated-sing-box-generator` manages sing-box deployment and WARP integration.
Modules involved:
- `src/automated_sing_box_generator/deploy.py`: `prompt_warp_mode()`, `deploy()`, `redeploy()`, `reconfigure()`, `show_status()`, `activate_server_config()`.
- `src/automated_sing_box_generator/installer.py`: `ensure_warp()`.
- `src/automated_sing_box_generator/watchdog.py`: `build_watchdog_script()`, `deploy_watchdog()`.
- `src/automated_sing_box_generator/cli.py`: `--warp-mode` argument, `cmd_deploy()`, `cmd_watchdog()`.
- `src/automated_sing_box_generator/config.py`: output configuration generator (already supports `warp_mode="none"`).

## Milestones

| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Exploration & Impact Assessment | Inspect existing implementation of prompt_warp_mode, ensure_warp, watchdog, activate_server_config, cli parser | None | DONE |
| M2 | Implementation of R1-R5 | Code updates across deploy.py, installer.py, watchdog.py, cli.py | M1 | DONE |
| M3 | Verification & Review | Run verification commands, test proxy/tun/direct/none cases, review diffs | M2 | IN_PROGRESS |
| M4 | Forensic Audit & Handoff | Conduct integrity audit, verify zero regressions, notify parent | M3 | PLANNED |

## Requirements Breakdown

### R1. prompt_warp_mode() accepts direct/none
- Input "direct" -> maps to "none"
- Input "none" -> valid "none"
- Check os.environ["WARP_MODE"] first
- Interactive prompt updated to `[proxy/tun/direct]`

### R2. ensure_warp() skips WARP when preferred_mode="none"
- Returns "none" immediately
- Calls ui.info() message

### R3. Watchdog handles none mode
- build_watchdog_script("none") -> None
- deploy_watchdog(warp_mode="none") -> returns silently
- deploy() skips watchdog deployment if warp_mode == "none"
- cmd_watchdog skips if state has warp_mode == "none"

### R4. activate_server_config() file targeting
- warp_mode == "none" -> target SING_BOX_DIRECT_CONFIG_PATH
- else -> SING_BOX_WARP_CONFIG_PATH

### R5. CLI --warp-mode and status display
- `--warp-mode` choices: ["proxy", "tun", "direct", "none"]
- `cmd_deploy` sets os.environ["WARP_MODE"] (mapping direct -> none)
- `show_status()` shows "direct (无 WARP)" and skips WARP readiness check

## Verification Plan
Execute the 6 python verification commands specified in ORIGINAL_REQUEST.md.
