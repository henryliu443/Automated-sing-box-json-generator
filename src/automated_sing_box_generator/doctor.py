"""Doctor module for automated system health and dependency checks."""

import os
import subprocess
import json

from . import ui
from .installer import (
    command_exists,
    get_singbox_version,
    warp_proxy_ready,
    warp_tunnel_ready,
    SYSTEM_RESOLV_CONF
)


def _check_systemd_service(service_name: str) -> bool:
    """Check if a systemd service is active."""
    try:
        res = subprocess.run(
            ["systemctl", "is-active", "--quiet", service_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return res.returncode == 0
    except Exception:
        return False


def _check_system_dns() -> str:
    """Check if system DNS is using Cloudflare."""
    try:
        with open(SYSTEM_RESOLV_CONF, "r") as f:
            content = f.read()
            if "1.1.1.1" in content or "1.0.0.1" in content:
                return "Configured (Cloudflare)"
            return "Other"
    except Exception as e:
        return f"Error: {e}"


def run_doctor():
    """Run comprehensive system health checks."""
    ui.banner("System Doctor", "Running diagnostic checks...")
    
    issues_found = 0

    ui.section("1. Dependencies & Commands")
    
    # Check sing-box
    sb_ver = get_singbox_version()
    if sb_ver:
        ui.success(f"sing-box: Installed ({sb_ver})")
    else:
        ui.error("sing-box: Not found or unusable")
        issues_found += 1

    # Check warp-cli
    if command_exists("warp-cli"):
        ui.success("warp-cli: Installed")
    else:
        ui.error("warp-cli: Not found")
        issues_found += 1

    # Check iproute2 (ss)
    if command_exists("ss"):
        ui.success("iproute2 (ss): Installed")
    else:
        ui.error("iproute2 (ss): Not found")
        issues_found += 1

    ui.section("2. Services & Daemons")
    
    # Check sing-box service
    if _check_systemd_service("sing-box"):
        ui.success("Service 'sing-box': Active")
    else:
        ui.error("Service 'sing-box': Inactive or failed")
        issues_found += 1

    # Check warp-svc service
    if _check_systemd_service("warp-svc"):
        ui.success("Service 'warp-svc': Active")
    else:
        ui.error("Service 'warp-svc': Inactive or failed")
        issues_found += 1

    ui.section("3. Network & Configs")

    # WARP state
    if warp_proxy_ready():
        ui.success("WARP State: Proxy Mode Ready")
    elif warp_tunnel_ready():
        ui.success("WARP State: TUN Mode Ready")
    else:
        ui.warning("WARP State: Not Ready / Unreachable")
        issues_found += 1

    # DNS configuration
    dns_status = _check_system_dns()
    if "Cloudflare" in dns_status:
        ui.success(f"System DNS: {dns_status}")
    else:
        ui.warning(f"System DNS: {dns_status} (Expected Cloudflare 1.1.1.1)")
        # Not explicitly an error since custom DNS might work, but warning is good

    # config.json check
    if os.path.isfile("/etc/sing-box/config.json"):
        ui.success("Config file: /etc/sing-box/config.json exists")
        # Ensure it is valid JSON
        try:
            with open("/etc/sing-box/config.json", "r") as f:
                json.load(f)
            ui.success("Config file: JSON parsed successfully")
        except json.JSONDecodeError as e:
            ui.error(f"Config file: Invalid JSON format - {e}")
            issues_found += 1
    else:
        ui.error("Config file: /etc/sing-box/config.json missing")
        issues_found += 1

    ui.section("Diagnostic Summary")
    if issues_found == 0:
        ui.success("All checks passed. System is healthy.")
    else:
        ui.error(f"Found {issues_found} issue(s) that require attention.")

    return issues_found
