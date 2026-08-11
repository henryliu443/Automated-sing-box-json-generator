# Codebase Analysis: Adding Direct (Alias "none") WARP Mode

## Executive Summary
This document provides a detailed codebase analysis for adding a `direct` (alias `"none"`) WARP mode to `automated-sing-box-generator`.
When `direct` / `"none"` WARP mode is selected:
1. `sing-box` outbound traffic routes directly (`{"type": "direct", "tag": "direct"}`) without tunneling through Cloudflare WARP.
2. WARP installation and verification (`ensure_warp`) are completely skipped.
3. WARP watchdog script deployment and cron job creation are skipped (`build_watchdog_script("none")` returns `None`).
4. Active `sing-box` config symlink points to `config.direct.json` instead of `config.warp.json`.
5. Existing `proxy` and `tun` WARP modes remain 100% untouched and functional.
6. `config.py` already supports `warp_mode="none"` out-of-the-box and requires **zero changes**.

---

## Detailed File Analysis & Proposed Changes

### 1. `src/automated_sing_box_generator/deploy.py`

#### A. `prompt_warp_mode()` (Lines 128-136)
- **Current Behavior**:
  Prompts the user interactively with `请选择 WARP 模式 [proxy/tun] (默认 proxy)`. Accepts `proxy` or `tun`, defaulting to `proxy`.
- **Requirements**:
  - Read `WARP_MODE` environment variable before prompting interactively (for CLI `--warp-mode` passthrough).
  - Map `direct` input / environment variable to `"none"`.
  - Accept `none` as valid input.
  - Update prompt string to `请选择 WARP 模式 [proxy/tun/direct] (默认 proxy)`.
- **Proposed Code Change**:
  ```python
  def prompt_warp_mode():
      ui.section("WARP 模式")
      env_mode = os.environ.get("WARP_MODE", "").strip().lower()
      if env_mode:
          if env_mode in ("direct", "none"):
              ui.info(f"使用环境变量 WARP_MODE: direct (none)")
              return "none"
          if env_mode in ("proxy", "tun"):
              ui.info(f"使用环境变量 WARP_MODE: {env_mode}")
              return env_mode

      raw = ui.prompt("请选择 WARP 模式 [proxy/tun/direct] (默认 proxy)").strip().lower()
      if not raw:
          return "proxy"
      if raw in ("direct", "none"):
          return "none"
      if raw in ("proxy", "tun"):
          return raw
      ui.warning(f"无效模式 {raw}，将使用默认 proxy")
      return "proxy"
  ```

#### B. `activate_server_config()` and Call Sites in `deploy()`, `redeploy()`, `reconfigure()`
- **Current Behavior**:
  - `activate_server_config(target=SING_BOX_WARP_CONFIG_PATH, link_path=SING_BOX_CONFIG_PATH)` (Line 180) defaults to `SING_BOX_WARP_CONFIG_PATH`.
  - All three deployment functions (`deploy()`, `redeploy()`, `reconfigure()`) generate both `config.warp.json` and `config.direct.json` but unconditionally call `activate_server_config()` without passing `target`.
- **Requirements**:
  - When `warp_mode == "none"`, pass `target=SING_BOX_DIRECT_CONFIG_PATH` to `activate_server_config()`.
  - Otherwise, pass `target=SING_BOX_WARP_CONFIG_PATH`.
- **Proposed Code Change**:
  In `deploy()` (around Line 306), `redeploy()` (around Line 388), and `reconfigure()` (around Line 461):
  ```python
  target_config = SING_BOX_DIRECT_CONFIG_PATH if warp_mode == "none" else SING_BOX_WARP_CONFIG_PATH
  activate_server_config(target=target_config)
  ```

#### C. Watchdog Deployment in `deploy()` (Lines 324-326)
- **Current Behavior**:
  Unconditionally calls `deploy_watchdog(WATCHDOG_SCRIPT_PATH, warp_mode=warp_mode)`.
- **Requirements**:
  Skip watchdog deployment when `warp_mode == "none"` and print an informative UI message.
- **Proposed Code Change**:
  ```python
  ui.section("守护任务")
  if warp_mode == "none":
      ui.info("直连模式 (none) 无需部署 WARP Watchdog")
  else:
      ui.step(f"部署 watchdog: {WATCHDOG_SCRIPT_PATH}")
      deploy_watchdog(WATCHDOG_SCRIPT_PATH, warp_mode=warp_mode)
  ```

#### D. `show_status()` (Lines 477, 498-503)
- **Current Behavior**:
  - Displays raw `loaded.get("warp_mode")` under state summary.
  - Runs WARP readiness checks (`warp_proxy_ready()`, `warp_tunnel_ready()`) under service status, showing `ui.warning("WARP 未就绪")` if neither is active.
- **Requirements**:
  - Display `"direct (无 WARP)"` when `warp_mode == "none"`.
  - Skip WARP readiness checks when `warp_mode == "none"`, printing `ui.info("WARP: 直连模式 (无 WARP)")`.
- **Proposed Code Change**:
  Under deployment state summary (Line 477):
  ```python
  warp_mode_display = "direct (无 WARP)" if loaded.get("warp_mode") == "none" else loaded.get("warp_mode", "?")
  ui.kv("WARP 模式", warp_mode_display)
  ```
  Under service status (Lines 498-503):
  ```python
  warp_mode = loaded.get("warp_mode") if loaded else None
  if warp_mode == "none":
      ui.info("WARP: 直连模式 (无 WARP)")
  elif warp_proxy_ready():
      ui.success("WARP: 本地代理模式正常")
  elif warp_tunnel_ready():
      ui.success("WARP: 系统隧道模式正常")
  else:
      ui.warning("WARP 未就绪")
  ```

---

### 2. `src/automated_sing_box_generator/installer.py`

#### Function `ensure_warp(preferred_mode=None)` (Lines 708-746)
- **Current Behavior**:
  - Validates `preferred_mode` against `(None, "proxy", "tun")`, raising `RuntimeError` for any other value.
  - Always checks `warp_proxy_ready()` and `warp_tunnel_ready()`, and installs Cloudflare WARP packages if not ready.
- **Requirements**:
  - Modify validation to allow `"none"`.
  - When `preferred_mode == "none"`, print `ui.info("已选择直连模式 (none)，跳过 WARP 安装与检测")` and immediately return `"none"`.
- **Proposed Code Change**:
  ```python
  def ensure_warp(preferred_mode=None):
      if preferred_mode not in (None, "proxy", "tun", "none"):
          raise RuntimeError(f"不支持的 WARP 模式: {preferred_mode}")

      if preferred_mode == "none":
          ui.info("已选择直连模式 (none)，跳过 WARP 安装与检测")
          return "none"

      if warp_proxy_ready():
          ui.success("检测到 WARP 本地代理模式 (127.0.0.1:40000)")
          return "proxy"
      ...
  ```
- **Note on `ensure_dependencies()` & `ensure_port_safety()`**:
  - In `ensure_dependencies()` (Lines 812-826), `warp_mode = ensure_warp(preferred_mode=preferred_warp_mode)` returns `"none"`.
  - `ensure_port_safety(warp_mode, ...)` (Line 285) only performs `assert_port_allowed/required` on WARP port `40000` if `warp_mode == "proxy"`. When `warp_mode == "none"`, port safety checks pass without inspecting WARP proxy ports. No further changes needed in `installer.py`.

---

### 3. `src/automated_sing_box_generator/watchdog.py`

#### A. `build_watchdog_script(warp_mode="proxy")` (Lines 32-44)
- **Current Behavior**:
  Raises `ValueError(f"unsupported warp_mode: {warp_mode}")` if `warp_mode` is not `"proxy"` or `"tun"`.
- **Requirements**:
  Return `None` when `warp_mode == "none"`.
- **Proposed Code Change**:
  ```python
  def build_watchdog_script(warp_mode="proxy"):
      if warp_mode == "none":
          return None
      if warp_mode == "proxy":
          check_block = _WARP_CHECK_PROXY
      elif warp_mode == "tun":
          check_block = _WARP_CHECK_TUN
      else:
          raise ValueError(f"unsupported warp_mode: {warp_mode}")

      template = _WATCHDOG_TEMPLATE.read_text(encoding="utf-8")
      script = template.replace("%%WARP_MODE%%", warp_mode)
      script = script.replace("%%WARP_CHECK_BLOCK%%", check_block)
      return script
  ```

#### B. `deploy_watchdog(script_path="/root/warp_lazy_watchdog.sh", warp_mode="proxy")` (Lines 46-54)
- **Current Behavior**:
  Unconditionally writes `build_watchdog_script(warp_mode)` to file and sets up a cron job.
- **Requirements**:
  When `warp_mode == "none"`, return silently without creating any file or installing a cron job.
- **Proposed Code Change**:
  ```python
  def deploy_watchdog(script_path="/root/warp_lazy_watchdog.sh", warp_mode="proxy"):
      if warp_mode == "none":
          return
      script = build_watchdog_script(warp_mode)
      if script is None:
          return
      with open(script_path, "w", encoding="utf-8") as f:
          f.write(script)
      os.chmod(script_path, 0o755)

      cron_line = f"* * * * * {script_path}"
      clean_cron = f'(crontab -l 2>/dev/null | grep -v "{script_path}"; echo "{cron_line}") | crontab -'
      subprocess.run(clean_cron, shell=True, check=True)
  ```

---

### 4. `src/automated_sing_box_generator/cli.py`

#### A. `build_parser()` (Lines 223-234)
- **Current Behavior**:
  `p_deploy` subcommand does not accept a `--warp-mode` flag.
- **Requirements**:
  Add `--warp-mode` option with choices `["proxy", "tun", "direct", "none"]`.
- **Proposed Code Change**:
  ```python
  p_deploy.add_argument("--warp-mode", choices=["proxy", "tun", "direct", "none"], default=None,
                        help="WARP 模式 (proxy/tun/direct/none)")
  ```

#### B. `cmd_deploy(args)` (Lines 49-70)
- **Current Behavior**:
  Processes CLI flags and calls `deploy.main(...)`.
- **Requirements**:
  When `--warp-mode` is provided on CLI, map `direct` -> `none` and pass it via `os.environ["WARP_MODE"]`.
- **Proposed Code Change**:
  ```python
  def cmd_deploy(args):
      if getattr(args, "warp_mode", None):
          mode = "none" if args.warp_mode in ("direct", "none") else args.warp_mode
          os.environ["WARP_MODE"] = mode
      protocols = _parse_protocols(args.protocols) if args.protocols else None
      ...
  ```

#### C. `cmd_watchdog(args)` (Lines 155-165)
- **Current Behavior**:
  Reads state and calls `watchdog.deploy_watchdog(..., warp_mode=warp_mode)`.
- **Requirements**:
  If state has `warp_mode == "none"`, display `ui.info("当前部署为直连模式 (none)，跳过 Watchdog 部署")` and return early without error.
- **Proposed Code Change**:
  ```python
  def cmd_watchdog(args):
      ui.banner("部署 Watchdog", "手动部署/更新 WARP 守护脚本")
      try:
          loaded = state_mod.load_state()
          warp_mode = loaded.get("warp_mode", "proxy") if loaded else "proxy"
          if warp_mode == "none":
              ui.info("当前部署为直连模式 (none)，跳过 Watchdog 部署")
              return
          watchdog.deploy_watchdog(deploy.WATCHDOG_SCRIPT_PATH, warp_mode=warp_mode)
          ui.success("Watchdog 守护脚本已部署")
      except RuntimeError as e:
          ui.error(str(e))
          sys.exit(1)
  ```

---

### 5. `src/automated_sing_box_generator/config.py`

#### Verification of `build_server_outbounds("none")` & `build_server_config()`
- **Implementation in `config.py`**:
  - `build_server_outbounds("none")` (Lines 176-177):
    ```python
    if warp_mode == "none":
        return [{"type": "direct", "tag": "direct"}]
    ```
  - `build_server_config()` (Lines 417, 431-435, 458-460):
    ```python
    outbound_tag = "warp-out" if warp_mode in ("proxy", "tun") else "direct"
    ...
    rules.append({
        "inbound": inbound_tags,
        "action": "route",
        "outbound": outbound_tag,
    })
    ...
    "route": {
        "rules": rules,
        "final": outbound_tag,
        "default_domain_resolver": SERVER_DNS_TAG,
    }
    ```
- **Conclusion**:
  When `warp_mode == "none"`, `build_server_outbounds("none")` returns `[{"type": "direct", "tag": "direct"}]`, `outbound_tag` evaluates to `"direct"`, all inbound rules route to `"direct"`, and `route.final` evaluates to `"direct"`.
  `config.py` is already 100% compliant with requirement R5/AC1. **Zero changes needed in `config.py`**.

---

## Matrix of Requirements vs. Files

| Requirement | Target File(s) | Functions Affected | Change Required |
|-------------|----------------|-------------------|-----------------|
| **R1** | `deploy.py` | `prompt_warp_mode()` | Check `WARP_MODE` env var, accept `direct` & `none`, prompt `[proxy/tun/direct]` |
| **R2** | `installer.py` | `ensure_warp()` | Return `"none"` with `ui.info` when `preferred_mode == "none"` |
| **R3** | `watchdog.py`, `deploy.py`, `cli.py` | `build_watchdog_script()`, `deploy_watchdog()`, `deploy()`, `cmd_watchdog()` | Return `None`/silent skip on `none` mode |
| **R4** | `deploy.py` | `deploy()`, `redeploy()`, `reconfigure()` | Symlink `config.json` -> `config.direct.json` when `warp_mode == "none"` |
| **R5** | `cli.py`, `deploy.py` | `build_parser()`, `cmd_deploy()`, `show_status()` | Add `--warp-mode` CLI flag, format status display `direct (无 WARP)` |
