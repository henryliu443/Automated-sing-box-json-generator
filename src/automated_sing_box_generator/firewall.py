from __future__ import annotations
"""OS-level network hardening firewall module (nftables).

Project positioning: secure-by-default deployment tool, NOT a high-security
baseline framework. This module applies low-risk hardening rules only.

Design principles:
- Default ACCEPT policy (not DROP) — reduces operational risk and lockout risk.
- Auto-detect SSH port from sshd_config — never hard-code port 22.
- No IP whitelist, no GeoIP, no country restrictions by default.
- UDP rate limiting is DISABLED by default (may impact QUIC/Hysteria2/TUIC).
- Advanced protections are opt-in only (--harden / firewall --enhanced).
- Primary anti-probe mechanisms remain at the protocol layer:
  Reality fingerprinting, Hysteria2 masquerading, Salamander obfuscation.
  This module handles: hardening, abuse mitigation, scan noise reduction.

Default safe rules applied:
  - Allow loopback traffic
  - Allow ESTABLISHED, RELATED connections
  - Drop INVALID state packets
  - Drop NULL scans (no flags)
  - Drop XMAS scans (FIN+PSH+URG)
  - Drop SYN-FIN scans
  - Drop ICMP timestamp requests (OS fingerprint reduction)
  - Conservative SSH connection rate limiting (configurable, not hard-coded)
"""

import os
import re
import subprocess
import shutil

from . import ui

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SINGBOX_TABLE = "singbox_guard"
SINGBOX_CHAIN_INPUT = "input_hardening"
SINGBOX_CHAIN_FORWARD = "forward_hardening"

NFT_CONF_PATH = "/etc/nftables.d/singbox-guard.conf"
NFT_CONF_DIR = "/etc/nftables.d"

SSHD_CONFIG_PATHS = (
    "/etc/ssh/sshd_config",
    "/etc/sshd_config",
)
SSHD_CONFIG_D = "/etc/ssh/sshd_config.d"

# Conservative SSH rate limiting defaults (intentionally permissive).
# No fixed IP assumptions: users connect from home/school/mobile/VPN/abroad.
SSH_RATELIMIT_INTERVAL = "60"    # seconds
SSH_RATELIMIT_BURST = "15"       # new connections per interval per source IP

# ---------------------------------------------------------------------------
# SSH port detection
# ---------------------------------------------------------------------------

def _detect_ssh_port() -> int:
    """Auto-detect SSH port from sshd_config. Never assume port 22."""
    port = _parse_sshd_port_from_files(SSHD_CONFIG_PATHS)
    if port:
        return port

    # Check sshd_config.d includes
    if os.path.isdir(SSHD_CONFIG_D):
        for fname in sorted(os.listdir(SSHD_CONFIG_D)):
            if fname.endswith(".conf"):
                p = _parse_sshd_port_from_files(
                    [os.path.join(SSHD_CONFIG_D, fname)]
                )
                if p:
                    return p

    # Fallback: query ss for what sshd is actually listening on
    try:
        result = subprocess.run(
            ["ss", "-tlnp"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines():
            if "sshd" in line:
                m = re.search(r":(\d+)\s", line)
                if m:
                    return int(m.group(1))
    except Exception:
        pass

    ui.warning("无法自动检测 SSH 端口，使用默认值 22（注意核实）")
    return 22


def _parse_sshd_port_from_files(paths) -> int:
    """Parse the first uncommented Port directive from sshd config files."""
    for path in paths:
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    stripped = line.strip()
                    if stripped.startswith("#"):
                        continue
                    m = re.match(r"^Port\s+(\d+)", stripped, re.IGNORECASE)
                    if m:
                        return int(m.group(1))
        except OSError:
            pass
    return 0


# ---------------------------------------------------------------------------
# nftables availability
# ---------------------------------------------------------------------------

def _nft_available() -> bool:
    return shutil.which("nft") is not None


def _run_nft(cmd: str, check=True) -> subprocess.CompletedProcess:
    """Run an nft command."""
    result = subprocess.run(
        ["nft"] + cmd.split(),
        capture_output=True, text=True,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"nft command failed: nft {cmd}\n"
            f"stderr: {result.stderr.strip()}"
        )
    return result


def _run_nft_input(nft_script: str) -> subprocess.CompletedProcess:
    """Feed a full nft script via stdin."""
    result = subprocess.run(
        ["nft", "-f", "-"],
        input=nft_script,
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"nft script failed:\n{nft_script}\nstderr: {result.stderr.strip()}"
        )
    return result


# ---------------------------------------------------------------------------
# nftables config persistence
# ---------------------------------------------------------------------------

def _ensure_nftables_d_include():
    """Ensure /etc/nftables.d/ is included from main nftables.conf."""
    main_conf = "/etc/nftables.conf"
    if not os.path.isfile(main_conf):
        return

    with open(main_conf, "r", encoding="utf-8") as f:
        content = f.read()

    include_line = f'include "{NFT_CONF_DIR}/*.conf"'
    if include_line not in content:
        # Append include directive
        with open(main_conf, "a", encoding="utf-8") as f:
            f.write(f"\n# Added by automated-sing-box-generator\n{include_line}\n")
        ui.info(f"已将 {NFT_CONF_DIR}/*.conf 加入 {main_conf}")


def _write_nft_conf(rules: str):
    """Write the nftables config file for persistence."""
    os.makedirs(NFT_CONF_DIR, mode=0o750, exist_ok=True)
    with open(NFT_CONF_PATH, "w", encoding="utf-8") as f:
        f.write(rules)
    os.chmod(NFT_CONF_PATH, 0o640)


# ---------------------------------------------------------------------------
# Rule builder
# ---------------------------------------------------------------------------

def _build_nft_ruleset(
    ssh_port: int,
    protocol_ports: list[tuple[int, str]] | None = None,
    ssh_ratelimit_interval: str = SSH_RATELIMIT_INTERVAL,
    ssh_ratelimit_burst: str = SSH_RATELIMIT_BURST,
    enable_udp_ratelimit: bool = False,
    tcp_connlimit: int = 0,
) -> str:
    """
    Build nftables ruleset string.

    Default hardening only (Default ACCEPT policy):
    - Allow loopback
    - Allow ESTABLISHED/RELATED
    - Drop INVALID
    - Drop NULL/XMAS/SYN-FIN TCP scans
    - Drop ICMP timestamp requests
    - Conservative SSH rate limiting

    UDP rate limiting is DISABLED by default — may impact QUIC/Hysteria2/TUIC.
    """
    proto_ports = protocol_ports or []

    lines = [
        "# singbox-guard: OS-level network hardening (generated by automated-sing-box-generator)",
        "# Default ACCEPT policy — targeted hardening rules only.",
        f"# SSH port: {ssh_port} (auto-detected from sshd_config)",
        "",
        f"table inet {SINGBOX_TABLE} {{",
        "",
        f"    chain {SINGBOX_CHAIN_INPUT} {{",
        "        type filter hook input priority filter - 10; policy accept;",
        "",
        "        # Allow loopback",
        "        iif lo accept",
        "",
        "        # Allow established and related connections",
        "        ct state established,related accept",
        "",
        "        # Drop INVALID state packets",
        "        ct state invalid drop",
        "",
        "        # --- TCP scan protection ---",
        "        # Drop NULL scan (no TCP flags)",
        "        tcp flags == 0x0 drop",
        "",
        "        # Drop XMAS scan (FIN+PSH+URG)",
        "        tcp flags & (fin|psh|urg) == (fin|psh|urg) drop",
        "",
        "        # Drop SYN+FIN (invalid combination)",
        "        tcp flags & (syn|fin) == (syn|fin) drop",
        "",
        "        # Drop SYN+RST (invalid combination)",
        "        tcp flags & (syn|rst) == (syn|rst) drop",
        "",
        "        # --- ICMP fingerprint reduction ---",
        "        # Drop ICMP timestamp requests (OS fingerprinting)",
        "        ip protocol icmp icmp type timestamp-request drop",
        "        ip6 nexthdr icmpv6 icmpv6 type 139 drop",
        "",
        "        # --- SSH rate limiting ---",
        f"        # Conservative: {ssh_ratelimit_burst} new connections per {ssh_ratelimit_interval}s per source IP.",
        "        # No IP whitelist — users connect from home/school/mobile/VPN/abroad.",
        f"        tcp dport {ssh_port} ct state new \\",
        f"            limit rate over {ssh_ratelimit_burst}/{ssh_ratelimit_interval}second burst {ssh_ratelimit_burst} packets \\",
        "            drop",
        "",
    ]

    # Optional TCP connection limit per IP for proxy ports
    if tcp_connlimit > 0:
        for port, transport in proto_ports:
            if transport == "tcp":
                lines += [
                    f"        # TCP connection limit per source IP on port {port}",
                    f"        tcp dport {port} ct count over {tcp_connlimit} drop",
                    "",
                ]

    # Optional UDP rate limiting (DISABLED by default — may impact QUIC/Hysteria2/TUIC)
    if enable_udp_ratelimit:
        for port, transport in proto_ports:
            if transport == "udp":
                lines += [
                    f"        # UDP rate limit on port {port} (optional, may impact QUIC/Hysteria2/TUIC throughput)",
                    f"        udp dport {port} limit rate over 200/second burst 500 packets drop",
                    "",
                ]

    lines += [
        "    }",
        "",
        f"    chain {SINGBOX_CHAIN_FORWARD} {{",
        "        type filter hook forward priority filter - 10; policy accept;",
        "        # Forward chain: allow all (proxy outbound traffic must pass through)",
        "    }",
        "",
        "}",
        "",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def deploy_firewall(
    protocol_ports: list[tuple[int, str]] | None = None,
    *,
    ssh_port: int | None = None,
    ssh_ratelimit_interval: str = SSH_RATELIMIT_INTERVAL,
    ssh_ratelimit_burst: str = SSH_RATELIMIT_BURST,
    enable_udp_ratelimit: bool = False,
    tcp_connlimit: int = 0,
) -> None:
    """
    Deploy OS-level network hardening rules via nftables.

    This is low-risk, default-ACCEPT hardening only. It does NOT change the
    default policy to DROP and does NOT block any legitimate traffic.

    Advanced features (UDP rate limiting, TCP connlimit) are opt-in only.

    Args:
        protocol_ports: list of (port, transport) from config.protocol_ports().
        ssh_port: SSH port override. Auto-detected from sshd_config if None.
        ssh_ratelimit_interval: Seconds window for SSH rate limiting.
        ssh_ratelimit_burst: Max new SSH connections per interval per source IP.
        enable_udp_ratelimit: Enable UDP rate limiting (default False — may
            impact TUIC/Hysteria2/QUIC throughput with multiple clients or
            speed tests).
        tcp_connlimit: Max concurrent TCP connections per source IP per proxy
            port (0 = disabled).
    """
    if not _nft_available():
        ui.warning("nft 命令不可用，跳过防火墙强化（建议安装 nftables）")
        return

    detected_ssh = ssh_port or _detect_ssh_port()
    ui.step(f"配置 nftables 网络加固规则 (SSH 端口: {detected_ssh})")

    ruleset = _build_nft_ruleset(
        ssh_port=detected_ssh,
        protocol_ports=protocol_ports,
        ssh_ratelimit_interval=ssh_ratelimit_interval,
        ssh_ratelimit_burst=ssh_ratelimit_burst,
        enable_udp_ratelimit=enable_udp_ratelimit,
        tcp_connlimit=tcp_connlimit,
    )

    # Remove existing table first (idempotent)
    _run_nft(f"delete table inet {SINGBOX_TABLE}", check=False)

    # Apply rules
    _run_nft_input(ruleset)
    ui.success("nftables 加固规则已应用")

    # Persist to file
    _write_nft_conf(ruleset)
    ui.info(f"规则已持久化到: {NFT_CONF_PATH}")

    # Ensure /etc/nftables.d/ is included in main config
    _ensure_nftables_d_include()

    # Enable nftables service for boot persistence
    try:
        subprocess.run(
            ["systemctl", "enable", "nftables"],
            capture_output=True, check=False,
        )
    except Exception:
        pass

    ui.success("OS 网络加固已完成（默认 ACCEPT + 针对性加固规则）")


def remove_firewall() -> None:
    """Remove the singbox_guard nftables table and persisted config file."""
    if not _nft_available():
        return

    ui.step("移除 nftables 加固规则")

    result = _run_nft(f"delete table inet {SINGBOX_TABLE}", check=False)
    if result.returncode == 0:
        ui.success("nftables 加固表已移除")
    else:
        ui.info("nftables 加固表不存在或已移除")

    if os.path.isfile(NFT_CONF_PATH):
        try:
            os.remove(NFT_CONF_PATH)
            ui.success(f"已删除配置文件: {NFT_CONF_PATH}")
        except OSError as e:
            ui.warning(f"删除配置文件失败: {e}")


def firewall_status() -> bool:
    """Check if singbox_guard table is active. Returns True if active."""
    if not _nft_available():
        ui.warning("nft 不可用，跳过防火墙状态检查")
        return False

    result = _run_nft(f"list table inet {SINGBOX_TABLE}", check=False)
    if result.returncode == 0:
        ui.success(f"nftables 加固 ({SINGBOX_TABLE}): 已激活")
        return True
    else:
        ui.warning(f"nftables 加固 ({SINGBOX_TABLE}): 未激活")
        return False
