# Original User Request

## 2026-08-08T11:24:24Z

Add a `direct` (alias `none`) WARP mode to an existing automated sing-box deployment CLI tool. When selected, sing-box outbound traffic goes direct (no WARP tunnel/proxy), WARP installation is skipped, and the WARP watchdog cron is not deployed. No new VPN software is introduced. Existing `proxy` and `tun` modes must remain fully functional.

Working directory: /Users/henry/Automated-sing-box-json-generator
Integrity mode: development

## Requirements

### R1. `prompt_warp_mode()` accepts `direct` and `none`

In `src/automated_sing_box_generator/deploy.py`, update `prompt_warp_mode()` to:
- Accept `direct` as user input, mapping it internally to `"none"`
- Accept `none` as valid input
- Check the `WARP_MODE` environment variable before prompting interactively (for CLI `--warp-mode` passthrough)
- Update the interactive prompt text to show `[proxy/tun/direct]`

### R2. `ensure_warp()` skips WARP when mode is `none`

In `src/automated_sing_box_generator/installer.py`, modify `ensure_warp()` so that when `preferred_mode="none"`, it immediately returns `"none"` without installing or checking WARP. Print an info message via `ui.info()`.

### R3. Watchdog handles `none` mode gracefully

In `src/automated_sing_box_generator/watchdog.py`:
- `build_watchdog_script("none")` returns `None` instead of raising `ValueError`
- `deploy_watchdog()` with `warp_mode="none"` silently returns without writing a script or installing a cron job

In `src/automated_sing_box_generator/deploy.py`:
- `deploy()` skips watchdog deployment when `warp_mode == "none"` (print info message instead)
- `cmd_watchdog` in `cli.py` shows info message and skips when state has `warp_mode == "none"`

### R4. `activate_server_config()` points to correct config file

In `src/automated_sing_box_generator/deploy.py`, in all three call sites (`deploy()`, `redeploy()`, `reconfigure()`):
- When `warp_mode == "none"`, symlink `config.json` → `config.direct.json`
- Otherwise, symlink `config.json` → `config.warp.json` (existing behavior)

### R5. CLI `--warp-mode` argument and status display

In `src/automated_sing_box_generator/cli.py`:
- Add `--warp-mode` argument to `deploy` subcommand with `choices=["proxy", "tun", "direct", "none"]`
- In `cmd_deploy`, set `os.environ["WARP_MODE"]` when `--warp-mode` is provided (map `direct` → `none`)

In `src/automated_sing_box_generator/deploy.py` `show_status()`:
- Display `"direct (无 WARP)"` when `warp_mode == "none"`
- Skip WARP readiness check when `warp_mode == "none"` (show info message instead of warning)

## Acceptance Criteria

### Functional correctness
- [ ] `build_server_outbounds("none")` returns `[{"type": "direct", "tag": "direct"}]`
- [ ] `build_watchdog_script("none")` returns `None` without raising
- [ ] `build_watchdog_script("proxy")` and `build_watchdog_script("tun")` still return non-None strings
- [ ] `ensure_warp(preferred_mode="none")` returns `"none"` without calling any warp-cli commands
- [ ] `ensure_warp(preferred_mode="proxy")` and `ensure_warp(preferred_mode="tun")` behavior is unchanged (verify the function signature and early-return guard haven't broken the existing paths)
- [ ] `prompt_warp_mode()` returns `"none"` when `WARP_MODE=direct` is in the environment
- [ ] `prompt_warp_mode()` returns `"none"` when `WARP_MODE=none` is in the environment
- [ ] `prompt_warp_mode()` returns `"proxy"` when `WARP_MODE` is not set (and input is empty)
- [ ] CLI parser accepts `--warp-mode direct` and `--warp-mode none` without error
- [ ] In `deploy()`, when `warp_mode == "none"`, the `activate_server_config()` call receives `SING_BOX_DIRECT_CONFIG_PATH` as target
- [ ] In `redeploy()` and `reconfigure()`, same conditional logic for `activate_server_config()`

### No regressions
- [ ] All existing `proxy` and `tun` code paths are unchanged in behavior
- [ ] `config.py` has zero modifications (it already supports `warp_mode="none"`)
- [ ] No new VPN-related imports, packages, or software introduced anywhere

### Verification commands
Run all of the following from the project root and confirm they pass:

```bash
python -c "
from src.automated_sing_box_generator.config import build_server_outbounds
assert build_server_outbounds('none') == [{'type': 'direct', 'tag': 'direct'}]
assert build_server_outbounds('proxy')[0]['type'] == 'socks'
assert build_server_outbounds('tun')[0]['tag'] == 'warp-out'
print('PASS: build_server_outbounds')
"

python -c "
from src.automated_sing_box_generator.watchdog import build_watchdog_script
assert build_watchdog_script('none') is None
assert isinstance(build_watchdog_script('proxy'), str)
assert isinstance(build_watchdog_script('tun'), str)
print('PASS: build_watchdog_script')
"

python -c "
import os
os.environ['WARP_MODE'] = 'direct'
from src.automated_sing_box_generator.deploy import prompt_warp_mode
result = prompt_warp_mode()
assert result == 'none', f'Expected none, got {result}'
print('PASS: prompt_warp_mode with WARP_MODE=direct')
"

python -c "
import os
os.environ['WARP_MODE'] = 'none'
from src.automated_sing_box_generator.deploy import prompt_warp_mode
result = prompt_warp_mode()
assert result == 'none', f'Expected none, got {result}'
print('PASS: prompt_warp_mode with WARP_MODE=none')
"

python -c "
from unittest.mock import patch, MagicMock
from src.automated_sing_box_generator import installer
ui_mock = MagicMock()
with patch.object(installer, 'ui', ui_mock):
    result = installer.ensure_warp(preferred_mode='none')
assert result == 'none'
ui_mock.info.assert_called()
print('PASS: ensure_warp(none)')
"

python -c "
from src.automated_sing_box_generator.cli import build_parser
parser = build_parser()
args = parser.parse_args(['deploy', '--warp-mode', 'direct', '--domain', 'test.com'])
assert args.warp_mode == 'direct'
print('PASS: CLI --warp-mode')
"
```
