# Adversarial Challenge Report: Direct (None) WARP Mode Watchdog and Installer Behavior

## Challenge Summary

**Overall risk assessment**: LOW

Empirical testing and adversarial stress-testing confirm that direct (none) WARP mode is correctly handled across the installer, watchdog, and status display modules. All early return paths, warning suppressions, and script generation bypasses work as specified without invoking `warp-cli` or making unnecessary file system / crontab modifications.

---

## Empirical Verification Results

| Target Check | Scenario | Expected Behavior | Actual Behavior | Result |
| :--- | :--- | :--- | :--- | :--- |
| **`ensure_warp()`** | `preferred_mode="none"` | Return `"none"`, invoke `ui.info()`, 0 `warp-cli` or readiness calls | Returned `"none"`, logged `ui.info("WARP 模式为 direct (none)，跳过 WARP 安装与检查")`, zero `warp-cli`/network/installer calls | **PASS** |
| **`ensure_warp()`** | `preferred_mode="proxy"` | Return `"proxy"` and run readiness check | Executed `warp_proxy_ready()` and returned `"proxy"` | **PASS** |
| **`ensure_warp()`** | `preferred_mode="invalid"` | Raise `RuntimeError` | Raised `RuntimeError("不支持的 WARP 模式: invalid")` | **PASS** |
| **`build_watchdog_script()`** | `warp_mode="none"` | Return `None` without exception | Returned `None` | **PASS** |
| **`build_watchdog_script()`** | `warp_mode="proxy"` | Return non-empty shell script with proxy check | Returned script containing `WARP_MODE="proxy"` and `--proxy "$WARP_PROXY"` | **PASS** |
| **`build_watchdog_script()`** | `warp_mode="tun"` | Return non-empty shell script with tun check | Returned script containing `WARP_MODE="tun"` and direct `curl` check | **PASS** |
| **`build_watchdog_script()`** | `warp_mode="invalid"` | Raise `ValueError` | Raised `ValueError("unsupported warp_mode: invalid")` | **PASS** |
| **`deploy_watchdog()`** | `warp_mode="none"` | No file I/O, no chmod, no `subprocess.run` / crontab edit | Zero file creation, zero `open()`/`chmod()`/`subprocess.run()` calls | **PASS** |
| **`deploy_watchdog()`** | `warp_mode="proxy"` | Write script to disk and invoke crontab | File written, `os.chmod` called, `crontab` command executed via `subprocess.run` | **PASS** |
| **`show_status()`** | `warp_mode="none"` | Print KV `"direct (无 WARP)"`, print `ui.info(...)`, skip readiness checks & warning | KV logged `"direct (无 WARP)"`, info logged `"WARP: 直连模式 (无 WARP)"`, readiness checks skipped, no `"WARP 未就绪"` warning | **PASS** |
| **`show_status()`** | `warp_mode="proxy"` (not ready) | Print KV `"proxy"`, execute readiness checks, emit warning if not ready | KV logged `"proxy"`, readiness checks executed, `"WARP 未就绪"` warning emitted | **PASS** |

---

## Challenges & Failure Mode Analysis

### [Low] Challenge 1: Direct function calls to `ensure_warp` with case variants (e.g. `"NONE"` or `"direct"`)
- **Assumption challenged**: Callers outside `prompt_warp_mode()` or `cmd_deploy()` might pass `"NONE"` or `"direct"` to `ensure_warp()`.
- **Attack scenario**: A caller invokes `ensure_warp(preferred_mode="direct")` assuming `"direct"` is accepted as an alias for `"none"`.
- **Blast radius**: `ensure_warp` raises `RuntimeError("不支持的 WARP 模式: direct")` because `ensure_warp()` only checks `if preferred_mode == "none":`.
- **Mitigation**: `prompt_warp_mode()` and `cli.py` map `"direct"` to `"none"` before calling `ensure_warp()`. However, `ensure_warp()` could optionally accept `"direct"` or perform `.lower()` as a extra safety guard.

### [Low] Challenge 2: Unclosed file handle in `run_cmd` during `show_status()` snapshot
- **Assumption challenged**: `run_cmd` cleans up process stdout streams after execution.
- **Attack scenario**: Running `show_status()` in Python 3.14 triggers `ResourceWarning: unclosed file <_io.TextIOWrapper ...>`.
- **Blast radius**: Minor noise in test logs; slight unclosed file descriptor leak if called repeatedly in long-running processes.
- **Mitigation**: Explicitly call `proc.stdout.close()` in `run_cmd()` after the process loop finishes.

---

## Stress Test Results

- **`ensure_warp(preferred_mode="none")` with mocked system commands**: Verified zero invocation of `warp-cli`, `systemctl`, `apt-get`, or network socket checks. → **PASS**
- **`deploy_watchdog(script_path="/nonexistent/dir/watchdog.sh", warp_mode="none")`**: Early return prevents any `FileNotFoundError` or permission exception since file opening is skipped. → **PASS**
- **`show_status()` with state missing `warp_mode`**: Gracefully defaults `warp_mode` to `"?"`, falls back to checking WARP readiness, and displays standard status without crashing. → **PASS**

---

## Unchallenged Areas

- **Systemd service lifecycle on Linux VPS**: Server-level systemd actions are out of scope for local empirical unit tests per `AGENTS.md` rules.
