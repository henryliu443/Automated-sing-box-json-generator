# Changes Report - Milestone 2 (R1-R5) Direct WARP Mode

## Overview
Implemented Milestone 2 requirements R1-R5 for direct WARP mode (alias `"none"`). When direct/none mode is selected, sing-box routes outbounds directly without WARP, WARP installation and checks are bypassed, and Watchdog cron deployment is skipped.

## Modified Files

### 1. `src/automated_sing_box_generator/deploy.py`
- Updated `prompt_warp_mode()`:
  - Checks `os.environ.get("WARP_MODE")` first, mapping `"direct"` and `"none"` to `"none"`.
  - Prompts with updated label `[proxy/tun/direct]`.
  - Accepts `"direct"` and `"none"` interactively, mapping both to `"none"`.
- Updated `activate_server_config()` call sites in `deploy()`, `redeploy()`, and `reconfigure()`:
  - Passes `target=SING_BOX_DIRECT_CONFIG_PATH` when `warp_mode == "none"`, and `SING_BOX_WARP_CONFIG_PATH` otherwise.
- Updated `deploy()`:
  - Skips `deploy_watchdog()` when `warp_mode == "none"` and prints info message via `ui.info()`.
- Updated `show_status()`:
  - Displays `"direct (无 WARP)"` for WARP mode KV output when `warp_mode == "none"`.
  - Prints `ui.info("WARP: 直连模式 (无 WARP)")` and skips WARP readiness checks when `warp_mode == "none"`.

### 2. `src/automated_sing_box_generator/installer.py`
- Updated `ensure_warp(preferred_mode)`:
  - When `preferred_mode == "none"`, prints `ui.info("WARP 模式为 direct (none)，跳过 WARP 安装与检查")` and immediately returns `"none"` without executing any `warp-cli` commands or installing packages.

### 3. `src/automated_sing_box_generator/watchdog.py`
- Updated `build_watchdog_script(warp_mode)`:
  - Returns `None` when `warp_mode == "none"` without raising `ValueError`.
- Updated `deploy_watchdog(script_path, warp_mode)`:
  - Returns silently when `warp_mode == "none"`.

### 4. `src/automated_sing_box_generator/cli.py`
- Updated `build_parser()`:
  - Added `--warp-mode` argument to `deploy` subcommand (`p_deploy`) with `choices=["proxy", "tun", "direct", "none"]`.
- Updated `cmd_deploy(args)`:
  - Maps `args.warp_mode == "direct"` to `"none"` and sets `os.environ["WARP_MODE"]`.
- Updated `cmd_watchdog(args)`:
  - Checks state for `warp_mode == "none"`, prints `ui.info()` message, and skips watchdog deployment.

## Test Execution Commands & Verification Results

### Command 1: 6 Verification Script Assertions
```bash
PYTHONPATH=src python3 -c "
from automated_sing_box_generator.config import build_server_outbounds
from automated_sing_box_generator.watchdog import build_watchdog_script
from automated_sing_box_generator.deploy import prompt_warp_mode
from automated_sing_box_generator.installer import ensure_warp
from automated_sing_box_generator.cli import build_parser
from unittest.mock import patch
import os

assert build_server_outbounds('none') == [{'type': 'direct', 'tag': 'direct'}]
assert build_watchdog_script('none') is None

os.environ['WARP_MODE'] = 'direct'
assert prompt_warp_mode() == 'none'

os.environ['WARP_MODE'] = 'none'
assert prompt_warp_mode() == 'none'

with patch('automated_sing_box_generator.ui.info') as mock_info:
    assert ensure_warp(preferred_mode='none') == 'none'
    assert mock_info.called

parser = build_parser()
args = parser.parse_args(['deploy', '--warp-mode', 'direct'])
assert args.warp_mode == 'direct'

print('ALL 6 VERIFICATIONS PASSED!')
"
```
**Result**: `ALL 6 VERIFICATIONS PASSED!` (Exit Code: 0)

### Command 2: Unit Test Suite Execution
```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```
**Result**: `Ran 11 tests in 0.008s - OK` (Exit Code: 0)
