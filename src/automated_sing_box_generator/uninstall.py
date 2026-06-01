"""Uninstall module for removing sing-box and related configurations."""

import os
import shutil
import subprocess
from . import ui
from .cloudflare_dns import cleanup_all_managed_records
from .installer import (
    SINGBOX_AUTO_UPDATE_SCRIPT,
    SINGBOX_AUTO_UPDATE_CRON_FILE,
)


def _run_silent(cmd):
    try:
        subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def run_uninstall(remove_warp=False):
    ui.banner("卸载工具", "清理部署的组件及配置")

    # 1. Stop and disable sing-box
    ui.step("停止并禁用 sing-box 服务...")
    _run_silent("systemctl stop sing-box")
    _run_silent("systemctl disable sing-box")

    # 2. Remove systemd unit
    ui.step("移除 sing-box systemd unit...")
    if os.path.exists("/etc/systemd/system/sing-box.service"):
        os.remove("/etc/systemd/system/sing-box.service")
    _run_silent("systemctl daemon-reload")

    # 3. Remove watchdog
    ui.step("移除 watchdog...")
    _run_silent('crontab -l 2>/dev/null | grep -v "/root/warp_lazy_watchdog.sh" | crontab -')
    if os.path.exists("/root/warp_lazy_watchdog.sh"):
        os.remove("/root/warp_lazy_watchdog.sh")

    # 4. Remove auto-update script
    ui.step("移除自动更新任务...")
    _run_silent(f'crontab -l 2>/dev/null | grep -v "{SINGBOX_AUTO_UPDATE_SCRIPT}" | crontab -')
    if os.path.exists(SINGBOX_AUTO_UPDATE_CRON_FILE):
        os.remove(SINGBOX_AUTO_UPDATE_CRON_FILE)
    if os.path.exists(SINGBOX_AUTO_UPDATE_SCRIPT):
        os.remove(SINGBOX_AUTO_UPDATE_SCRIPT)

    # 5. Remove firewall rules
    ui.step("移除 nftables 网络加固规则...")
    try:
        from .firewall import remove_firewall
        remove_firewall()
    except Exception as e:
        ui.warning(f"清理防火墙规则失败: {e}")

    # 6. Clean Cloudflare DNS
    ui.step("清理 Cloudflare DNS 记录...")
    try:
        cleanup_all_managed_records()
    except Exception as e:
        ui.warning(f"清理 DNS 记录失败: {e}")

    # 7. Remove TLS Certs
    ui.step("移除 TLS 证书目录...")
    if os.path.exists("/etc/sing-box-certs"):
        shutil.rmtree("/etc/sing-box-certs", ignore_errors=True)

    # 8. Remove sing-box config dir
    ui.step("移除 sing-box 配置目录...")
    if os.path.exists("/etc/sing-box"):
        shutil.rmtree("/etc/sing-box", ignore_errors=True)
    if os.path.exists("/usr/bin/sing-box"):
        os.remove("/usr/bin/sing-box")

    # 8. Remove deploy state
    ui.step("移除部署状态记录...")
    if os.path.exists("/etc/sing-box-deploy"):
        shutil.rmtree("/etc/sing-box-deploy", ignore_errors=True)

    # 9. WARP
    if remove_warp:
        ui.step("卸载 WARP (cloudflare-warp)...")
        _run_silent("warp-cli --accept-tos disconnect")
        _run_silent("warp-cli --accept-tos delete")
        _run_silent("apt-get remove -y cloudflare-warp || yum remove -y cloudflare-warp || dnf remove -y cloudflare-warp")
    else:
        ui.info("跳过卸载 WARP (未提供 --remove-warp)")

    ui.success("卸载完成！系统已清理干净。")
