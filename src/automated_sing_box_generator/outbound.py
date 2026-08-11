import os
import subprocess
from . import ui
from . import state as state_mod

def check_dns_resolvable(host: str, timeout: float = 3.0) -> bool:
    """检查指定的 Host 能否在 timeout 内成功解析 DNS。"""
    import socket
    import concurrent.futures

    for family in (socket.AF_INET, socket.AF_INET6):
        try:
            socket.inet_pton(family, host)
            return True
        except socket.error:
            pass

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(socket.getaddrinfo, host, None)
        try:
            future.result(timeout=timeout)
            return True
        except (concurrent.futures.TimeoutError, socket.gaierror):
            return False

SING_BOX_CONFIG_PATH = "/etc/sing-box/config.json"
PROFILE_MAP = {
    "warp":      "/etc/sing-box/profiles/config.warp.json",
    "wireguard": "/etc/sing-box/profiles/config.wireguard.json",
    "direct":    "/etc/sing-box/profiles/config.direct.json",
}

def list_available_profiles() -> dict[str, bool]:
    """检查每个 profile 文件是否存在，返回 {name: exists}。"""
    return {name: os.path.exists(path) for name, path in PROFILE_MAP.items()}

def get_active_profile() -> str | None:
    """读取 config.json symlink 指向，匹配到 profile name。"""
    if not os.path.islink(SING_BOX_CONFIG_PATH):
        return None
    try:
        target = os.readlink(SING_BOX_CONFIG_PATH)
        target_name = os.path.basename(target)
        for name, path in PROFILE_MAP.items():
            if target_name == os.path.basename(path):
                return name
    except OSError:
        pass
    return None

def get_outbound_ip_snapshot(active_profile: str) -> str:
    """获取当前出口的 IP 映像。"""
    # 如果当前是 warp 且 warp 在 proxy 模式下运行，可以通过 socks5 代理测试 IP
    if active_profile == "warp":
        try:
            res = subprocess.run(
                ["curl", "-s", "-m", "5", "--socks5-hostname", "127.0.0.1:40000", "https://api.ipify.org"],
                capture_output=True, text=True
            )
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip()
        except Exception:
            pass

    # 通用直接检测（适用于 direct 模式或 tun 模式）
    try:
        res = subprocess.run(
            ["curl", "-s", "-m", "5", "https://api.ipify.org"],
            capture_output=True, text=True
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass

    return "未知"

def switch_outbound(target: str):
    """即时切换出口。"""
    ui.section(f"切换出口 -> {target}")
    if target not in PROFILE_MAP:
        ui.error(f"不支持的出口目标: {target}")
        return

    profile_path = PROFILE_MAP[target]
    if not os.path.exists(profile_path):
        ui.error(f"出口 profile 不存在: {profile_path}。请先添加该出口。")
        return

    # 前置依赖检查与服务状态同步
    if target == "warp":
        subprocess.run(["systemctl", "enable", "--now", "warp-svc"], check=False)
        from .installer import warp_proxy_ready, warp_tunnel_ready
        if not (warp_proxy_ready() or warp_tunnel_ready()):
            ui.error("WARP 服务未就绪/未运行！请先运行 'automated-sing-box-generator manage outbound add warp'。")
            return
        loaded = state_mod.load_state() or {}
        from . import watchdog, deploy
        watchdog.deploy_watchdog(deploy.WATCHDOG_SCRIPT_PATH, warp_mode=loaded.get("warp_mode", "proxy"))
    else:
        subprocess.run(["systemctl", "stop", "warp-svc"], check=False)
        subprocess.run(["systemctl", "disable", "warp-svc"], check=False)
        subprocess.run("crontab -l 2>/dev/null | grep -v warp_lazy_watchdog.sh | crontab -", shell=True)
        if target == "wireguard":
            loaded = state_mod.load_state() or {}
            endpoint_host = None
            wg_p = loaded.get("wg_params")
            if isinstance(wg_p, list) and wg_p:
                endpoint_host = wg_p[0].get("endpoint_host")
            elif isinstance(wg_p, dict):
                endpoint_host = wg_p.get("endpoint_host")
            if endpoint_host:
                ui.step(f"校验 WireGuard 终点 DNS 解析: {endpoint_host}")
                if not check_dns_resolvable(endpoint_host, timeout=3.0):
                    ui.error(f"无法解析 WireGuard 终点 DNS: {endpoint_host}，切换已终止。请检查网络连接。")
                    return

    # 读取旧的 symlink，以便在校验失败时回滚
    old_target = None
    if os.path.islink(SING_BOX_CONFIG_PATH):
        try:
            old_target = os.readlink(SING_BOX_CONFIG_PATH)
        except OSError:
            pass

    # 切换链接
    try:
        os.makedirs(os.path.dirname(SING_BOX_CONFIG_PATH), exist_ok=True)
        subprocess.run(["ln", "-sfn", profile_path, SING_BOX_CONFIG_PATH], check=True)
    except Exception as e:
        ui.error(f"更新配置软链接失败: {e}")
        return

    # 校验配置
    ui.step("校验 sing-box 配置")
    res = subprocess.run(["sing-box", "check", "-C", "/etc/sing-box"], capture_output=True, text=True)
    if res.returncode != 0:
        ui.error("sing-box 配置校验失败！")
        if res.stderr:
            print(res.stderr.strip())
        # 回滚链接
        if old_target:
            subprocess.run(["ln", "-sfn", old_target, SING_BOX_CONFIG_PATH])
        else:
            try:
                os.remove(SING_BOX_CONFIG_PATH)
            except OSError:
                pass
        return

    # 重启服务
    ui.step("重启 sing-box 服务")
    res_restart = subprocess.run(["systemctl", "restart", "sing-box"], capture_output=True, text=True)
    if res_restart.returncode != 0:
        ui.error("重启 sing-box 服务失败！")
        if res_restart.stderr:
            print(res_restart.stderr.strip())
        return

    ui.success(f"成功切换活跃出口为: {target}")

    # 更新状态文件
    try:
        loaded = state_mod.load_state()
        if loaded:
            loaded["active_outbound"] = target
            state_mod.save_state(loaded)
    except Exception as e:
        ui.warning(f"更新部署状态失败: {e}")

    # 显示新 IP
    ui.step("检测当前出口 IP")
    ip = get_outbound_ip_snapshot(target)
    ui.kv("出口 IP", ip)

def show_outbound_status():
    """显示出口状态信息。"""
    loaded = state_mod.load_state()
    if not loaded:
        ui.warning("未找到部署状态")
        return

    active = get_active_profile() or loaded.get("active_outbound", "unknown")
    available = list_available_profiles()

    ui.section("出口状态")
    ui.kv("当前活跃出口", active)

    ui.section("可用 Profiles")
    for name, exists in available.items():
        status_char = "✓" if exists else "✗"
        path = PROFILE_MAP[name]
        info_str = f"{status_char} {name:<10} ({path})"
        if name == active:
            ui.success(f" {info_str} [活跃]")
        else:
            if exists:
                ui.info(f" {info_str}")
            else:
                ui.warning(f" {info_str} (未配置)")

    ui.section("出口 IP 检测")
    ip = get_outbound_ip_snapshot(active)
    ui.kv("当前实际出口 IP", ip)

def add_outbound_profile(outbound_type: str, wg_content: str = None):
    """添加或更新出口 profile。"""
    ui.section(f"添加/更新出口: {outbound_type}")

    from . import deploy
    from . import installer

    loaded = state_mod.load_state()
    if not loaded:
        ui.error("未找到部署状态，请先进行初始化部署 (deploy)")
        return

    creds = loaded["credentials"]
    phosts = loaded["protocol_hosts"]
    enabled_protocols = loaded.get("enabled_protocols", [])
    opts = loaded.get("anti_detection")

    if outbound_type == "wireguard":
        from .wireguard import read_wg_configs_interactive, parse_wg_config
        if wg_content:
            configs = [c.strip() for c in wg_content.split("\n---\n") if c.strip()]
        else:
            configs = read_wg_configs_interactive()

        if not configs:
            ui.error("WireGuard 配置不能为空")
            return

        try:
            wg_params = [parse_wg_config(c) for c in configs]
        except Exception as e:
            ui.error(f"解析 WireGuard 配置失败: {e}")
            return

        ui.step("生成 WireGuard 服务端配置")
        server_config_wg = deploy.build_server_config(
            creds, phosts, warp_mode="wireguard",
            enabled_protocols=enabled_protocols, fingerprint_opts=opts,
            wg_params=wg_params
        )

        try:
            deploy.write_server_config(server_config_wg, deploy.SING_BOX_WG_CONFIG_PATH)
            ui.success(f"已写入: {deploy.SING_BOX_WG_CONFIG_PATH}")
        except Exception as e:
            ui.error(f"写入配置文件失败: {e}")
            return

        loaded["wg_params"] = wg_params
        state_mod.save_state(loaded)
        ui.success("部署状态已更新")

        active = loaded.get("active_outbound")
        if active == "wireguard":
            ui.step("当前活跃出口为 wireguard，重新加载服务...")
            switch_outbound("wireguard")

    elif outbound_type == "warp":
        ui.step("配置 Cloudflare WARP 依赖")
        try:
            preferred_mode = loaded.get("preferred_warp_mode") or "proxy"
            if preferred_mode not in ("proxy", "tun"):
                preferred_mode = "proxy"

            actual_mode = installer.ensure_warp(preferred_mode)
            ui.success(f"WARP 已就绪 (当前模式: {actual_mode})")
        except Exception as e:
            ui.error(f"配置 WARP 依赖失败: {e}")
            return

        ui.step("生成 WARP 服务端配置")
        server_config_warp = deploy.build_server_config(
            creds, phosts, warp_mode=actual_mode,
            enabled_protocols=enabled_protocols, fingerprint_opts=opts
        )

        try:
            deploy.write_server_config(server_config_warp, deploy.SING_BOX_WARP_CONFIG_PATH)
            ui.success(f"已写入: {deploy.SING_BOX_WARP_CONFIG_PATH}")
        except Exception as e:
            ui.error(f"写入配置文件失败: {e}")
            return

        # 部署 Watchdog
        ui.step("部署 Watchdog")
        from . import watchdog
        try:
            watchdog.deploy_watchdog(deploy.WATCHDOG_SCRIPT_PATH, warp_mode=actual_mode)
            ui.success("Watchdog 守护脚本已部署")
        except Exception as e:
            ui.warning(f"部署 Watchdog 失败: {e}")

        loaded["warp_mode"] = actual_mode
        loaded["preferred_warp_mode"] = preferred_mode
        state_mod.save_state(loaded)
        ui.success("部署状态已更新")

        active = loaded.get("active_outbound")
        if active in ("proxy", "tun", "warp"):
            ui.step("当前活跃出口包含 WARP，重新加载服务...")
            switch_outbound("warp")
