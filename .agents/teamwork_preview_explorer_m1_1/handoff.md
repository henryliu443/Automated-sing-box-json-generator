# Handoff Report: Milestone 1 Exploration & Codebase Analysis (Direct WARP Mode)

## 1. Observation

### Codebase Locations & Verbatim Code Inspection

1. **`src/automated_sing_box_generator/config.py`**:
   - Lines 155-180 (`build_server_outbounds`):
     ```python
     def build_server_outbounds(warp_mode):
         if warp_mode == "proxy":
             ...
         if warp_mode == "tun":
             ...
         if warp_mode == "none":
             return [{"type": "direct", "tag": "direct"}]
         raise ValueError(f"unsupported warp_mode: {warp_mode}")
     ```
   - Lines 417 (`build_server_config`):
     ```python
     outbound_tag = "warp-out" if warp_mode in ("proxy", "tun") else "direct"
     ```
   - Observation: `build_server_outbounds("none")` already returns `[{"type": "direct", "tag": "direct"}]` and `build_server_config` routes inbound traffic directly to `"direct"` when `warp_mode == "none"`.

2. **`src/automated_sing_box_generator/deploy.py`**:
   - Lines 128-136 (`prompt_warp_mode`):
     ```python
     def prompt_warp_mode():
         ui.section("WARP 模式")
         raw = ui.prompt("请选择 WARP 模式 [proxy/tun] (默认 proxy)").strip().lower()
         if not raw:
             return "proxy"
         if raw in {"proxy", "tun"}:
             return raw
         ui.warning(f"无效模式 {raw}，将使用默认 proxy")
         return "proxy"
     ```
     Observation: Does not check `WARP_MODE` environment variable and does not accept `direct` or `none`.
   - Line 180 (`activate_server_config`):
     ```python
     def activate_server_config(target=SING_BOX_WARP_CONFIG_PATH, link_path=SING_BOX_CONFIG_PATH):
     ```
     Observation: Defaults to `SING_BOX_WARP_CONFIG_PATH`. Callers in `deploy()`, `redeploy()`, `reconfigure()` do not pass `target`.
   - Lines 325-326 (`deploy` watchdog call):
     ```python
     deploy_watchdog(WATCHDOG_SCRIPT_PATH, warp_mode=warp_mode)
     ```
     Observation: Unconditionally calls `deploy_watchdog()` regardless of `warp_mode`.
   - Lines 477, 498-503 (`show_status`):
     ```python
     ui.kv("WARP 模式", loaded.get("warp_mode", "?"))
     ...
     if warp_proxy_ready():
         ui.success("WARP: 本地代理模式正常")
     elif warp_tunnel_ready():
         ui.success("WARP: 系统隧道模式正常")
     else:
         ui.warning("WARP 未就绪")
     ```
     Observation: Always attempts to verify WARP proxy/tunnel readiness, warning if inactive even when `warp_mode == "none"`.

3. **`src/automated_sing_box_generator/installer.py`**:
   - Lines 708-710 (`ensure_warp`):
     ```python
     def ensure_warp(preferred_mode=None):
         if preferred_mode not in (None, "proxy", "tun"):
             raise RuntimeError(f"不支持的 WARP 模式: {preferred_mode}")
     ```
     Observation: Raises `RuntimeError` if `preferred_mode` is `"none"`.

4. **`src/automated_sing_box_generator/watchdog.py`**:
   - Lines 32-38 (`build_watchdog_script`):
     ```python
     def build_watchdog_script(warp_mode="proxy"):
         if warp_mode == "proxy":
             check_block = _WARP_CHECK_PROXY
         elif warp_mode == "tun":
             check_block = _WARP_CHECK_TUN
         else:
             raise ValueError(f"unsupported warp_mode: {warp_mode}")
     ```
     Observation: Raises `ValueError` when `warp_mode == "none"`.
   - Lines 46-53 (`deploy_watchdog`):
     Observation: Unconditionally writes script and updates crontab.

5. **`src/automated_sing_box_generator/cli.py`**:
   - Lines 223-233 (`build_parser`):
     Observation: `p_deploy` subcommand does not contain `--warp-mode` flag.
   - Lines 155-165 (`cmd_watchdog`):
     Observation: Does not check if `warp_mode == "none"` before calling `deploy_watchdog`.

---

## 2. Logic Chain

1. **`config.py` Readiness**:
   - *Observation*: `config.py` line 176 returns `[{"type": "direct", "tag": "direct"}]` for `warp_mode == "none"`, and line 417 sets `outbound_tag = "direct"`.
   - *Deduction*: Server configuration generation for direct WARP mode is fully supported. No modification to `config.py` is needed.

2. **Environment & Interactive Passthrough**:
   - *Observation*: `deploy.py` line 128 prompts interactively without checking `os.environ.get("WARP_MODE")`. `cli.py` line 223 lacks `--warp-mode`.
   - *Deduction*: Adding `--warp-mode` to `cli.py` and setting `os.environ["WARP_MODE"]` in `cmd_deploy` will allow non-interactive passthrough. Updating `prompt_warp_mode()` to check `os.environ["WARP_MODE"]` first, and accepting `direct` (mapped to `none`) and `none` interactively, fulfills R1 and R5.

3. **Bypassing WARP Dependency Installation**:
   - *Observation*: `installer.py` line 708 rejects `preferred_mode="none"`.
   - *Deduction*: Allowing `"none"` in `ensure_warp()` and returning `"none"` immediately with `ui.info(...)` skips package installation, CLI checks, and daemon configuration, satisfying R2 without affecting existing `proxy`/`tun` logic.

4. **Watchdog Bypass**:
   - *Observation*: `watchdog.py` line 38 raises `ValueError` for `warp_mode="none"`. `deploy.py` line 326 and `cli.py` line 160 unconditionally attempt deployment.
   - *Deduction*: Updating `build_watchdog_script("none")` to return `None`, `deploy_watchdog()` to silently return when `warp_mode == "none"`, `deploy()` to print `ui.info()` and skip `deploy_watchdog()`, and `cmd_watchdog()` to print `ui.info()` and return early fulfills R3.

5. **Config Symlink Alignment**:
   - *Observation*: `activate_server_config()` in `deploy.py` defaults to `config.warp.json`.
   - *Deduction*: Passing `target=SING_BOX_DIRECT_CONFIG_PATH` when `warp_mode == "none"` in `deploy()`, `redeploy()`, and `reconfigure()` ensures `config.json` correctly points to `config.direct.json`, satisfying R4.

6. **Status Output & Verification Safety**:
   - *Observation*: `show_status()` line 502 shows `WARP 未就绪` warning when WARP is not active.
   - *Deduction*: Checking `warp_mode == "none"` in `show_status()` to display `"direct (无 WARP)"` and print `ui.info("WARP: 直连模式 (无 WARP)")` prevents false warnings on direct deployments.

---

## 3. Caveats

1. **No Live VPS Operations**:
   - Per `AGENTS.md`, live VPS commands (deployments, service restarts, package installations) were not executed.
   - Verification will be conducted in M3 using unit test suites / Python verification scripts and mock environments.
2. **Environment Variable Precedence**:
   - When `--warp-mode` is passed on CLI, `cmd_deploy` sets `os.environ["WARP_MODE"]`. `prompt_warp_mode()` must prioritize `WARP_MODE` over interactive prompting.

---

## 4. Conclusion

Adding direct (alias `none`) WARP mode is completely feasible with minimal, clean edits across 4 files (`deploy.py`, `installer.py`, `watchdog.py`, `cli.py`). `config.py` requires zero changes.

All five requirements (R1–R5) are clearly scoped with exact `before -> after` code changes documented in `analysis.md`. The design ensures 100% backward compatibility for existing `proxy` and `tun` modes.

---

## 5. Verification Method

To verify the implementation during Milestone 3:

1. **Unit Test Execution**:
   Run python unit test suite (e.g. `pytest` or `python -m unittest` script):
   ```bash
   python -c "
   from automated_sing_box_generator.config import build_server_outbounds, build_server_config
   from automated_sing_box_generator.watchdog import build_watchdog_script
   from automated_sing_box_generator.installer import ensure_warp

   # AC1: Outbounds
   assert build_server_outbounds('none') == [{'type': 'direct', 'tag': 'direct'}]

   # AC2: Watchdog
   assert build_watchdog_script('none') is None
   assert build_watchdog_script('proxy') is not None
   assert build_watchdog_script('tun') is not None

   # AC3: ensure_warp return
   assert ensure_warp(preferred_mode='none') == 'none'
   print('Milestone 1 Verification Assertions Passed!')
   "
   ```

2. **Environment Variable Passthrough Test**:
   ```bash
   WARP_MODE=direct python -c "
   from automated_sing_box_generator.deploy import prompt_warp_mode
   assert prompt_warp_mode() == 'none'
   "
   WARP_MODE=none python -c "
   from automated_sing_box_generator.deploy import prompt_warp_mode
   assert prompt_warp_mode() == 'none'
   "
   ```

3. **CLI Argument Parser Test**:
   ```bash
   python -c "
   from automated_sing_box_generator.cli import build_parser
   parser = build_parser()
   args = parser.parse_args(['deploy', '--warp-mode', 'direct'])
   assert args.warp_mode == 'direct'
   args2 = parser.parse_args(['deploy', '--warp-mode', 'none'])
   assert args2.warp_mode == 'none'
   print('CLI parser tests passed!')
   "
   ```

4. **Invalidation Conditions**:
   - If `build_watchdog_script("none")` raises `ValueError`.
   - If `ensure_warp(preferred_mode="none")` attempts to execute `warp-cli`.
   - If `activate_server_config()` symlinks `config.warp.json` when `warp_mode == "none"`.
