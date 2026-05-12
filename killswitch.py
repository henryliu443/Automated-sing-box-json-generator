"""Generate VPS VPN control-plane and kill-switch assets.

The installed assets keep decisions in vpnctl.  nftables, systemd, and
sing-box remain execution/runtime layers.
"""
import os
import subprocess
import textwrap

import cli_ui as ui


VPNKS_NFT_PATH = "/etc/nftables.d/vpn-killswitch.nft"
VPN_SAFETY_REFRESH_PATH = "/usr/local/sbin/vpn-safety-refresh"
VPNCTL_PATH = "/usr/local/sbin/vpnctl"
VPNKS_SERVICE = "vpn-killswitch"
VPNKS_SERVICE_UNIT_PATH = f"/etc/systemd/system/{VPNKS_SERVICE}.service"
VPNKS_STATE_DIR = "/run/vpnctl"
VPNKS_STATE_FILE = f"{VPNKS_STATE_DIR}/state"
VPNKS_ENGAGE_HOST = "engage.cloudflareclient.com"
WARP_TRACE_URL = "https://www.cloudflare.com/cdn-cgi/trace"
WARP_PROXY_URL = "socks5h://127.0.0.1:40000"


VPN_SAFETY_REFRESH_SCRIPT = f"""#!/usr/bin/env bash
set -euo pipefail

PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
umask 022

ENGAGE_HOST="${{VPNKS_ENGAGE_HOST:-{VPNKS_ENGAGE_HOST}}}"
NFT_PATH="${{VPNKS_NFT_PATH:-{VPNKS_NFT_PATH}}}"
WARP_PORTS="${{VPNKS_WARP_PORTS:-2408, 443, 500, 4500}}"
TUN_IFACES="${{VPNKS_TUN_IFACES:-sb-tun0 CloudflareWARP warp0}}"

need_cmd() {{
    command -v "$1" >/dev/null 2>&1 || {{
        echo "missing required command: $1" >&2
        exit 127
    }}
}}

ifname_elements() {{
    local out="" item
    for item in $TUN_IFACES; do
        [ -n "$item" ] || continue
        if [ -n "$out" ]; then
            out="$out, "
        fi
        out="$out\\"$item\\""
    done
    printf '%s' "$out"
}}

detect_ssh_ports() {{
    if ! command -v ss >/dev/null 2>&1; then
        printf '22'
        return
    fi

    local ports
    ports="$(ss -Hltpn 2>/dev/null | awk '
        /sshd/ {{
            for (i = 1; i <= NF; i++) {{
                if ($i ~ /:[0-9]+$/) {{
                    sub(/^.*:/, "", $i)
                    print $i
                }}
            }}
        }}
    ' | sort -un | paste -sd, -)"
    printf '%s' "${{ports:-22}}"
}}

need_cmd getent
need_cmd nft
need_cmd awk
need_cmd paste

v4="$(getent ahostsv4 "$ENGAGE_HOST" 2>/dev/null | awk '{{ print $1 }}' | sort -u | paste -sd, - || true)"
v6="$(getent ahostsv6 "$ENGAGE_HOST" 2>/dev/null | awk '{{ print $1 }}' | sort -u | paste -sd, - || true)"

if [ -z "$v4" ] && [ -z "$v6" ]; then
    echo "failed to resolve $ENGAGE_HOST" >&2
    exit 1
fi

tun_ifaces="$(ifname_elements)"
ssh_ports="${{VPNKS_SSH_PORTS:-$(detect_ssh_ports)}}"
mkdir -p "$(dirname "$NFT_PATH")"
tmp="$(mktemp "${{NFT_PATH}}.XXXXXX")"
trap 'rm -f "$tmp"' EXIT

cat > "$tmp" <<NFT
table inet vpnks {{
  set tun_ifaces {{
    type ifname
    elements = {{ $tun_ifaces }}
  }}

  set warp4 {{
    type ipv4_addr
    flags interval
    elements = {{ $v4 }}
  }}

  set warp6 {{
    type ipv6_addr
    flags interval
    elements = {{ $v6 }}
  }}

  chain output {{
    type filter hook output priority filter; policy accept;

    oifname "lo" accept
    ct state established,related accept
    tcp sport {{ $ssh_ports }} accept

    oifname @tun_ifaces accept

    ip daddr @warp4 udp dport {{ $WARP_PORTS }} accept
    ip6 daddr @warp6 udp dport {{ $WARP_PORTS }} accept

    ip daddr {{
      0.0.0.0/8,
      10.0.0.0/8,
      100.64.0.0/10,
      127.0.0.0/8,
      169.254.0.0/16,
      172.16.0.0/12,
      192.168.0.0/16,
      224.0.0.0/4,
      240.0.0.0/4,
      255.255.255.255/32
    }} accept

    ip6 daddr {{
      ::1/128,
      fc00::/7,
      fe80::/10,
      ff00::/8
    }} accept

    ip daddr 0.0.0.0/0 reject with icmpx admin-prohibited
    ip6 daddr ::/0 reject with icmpx admin-prohibited
  }}
}}
NFT

nft -c -f "$tmp"
install -m 0644 "$tmp" "$NFT_PATH"
trap - EXIT
rm -f "$tmp"

echo "resolved $ENGAGE_HOST"
echo "ipv4: ${{v4:-none}}"
echo "ipv6: ${{v6:-none}}"
echo "wrote $NFT_PATH"
"""


VPNCTL_SCRIPT = f"""#!/usr/bin/env bash
set -euo pipefail

PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

STATE_DIR="{VPNKS_STATE_DIR}"
STATE_FILE="{VPNKS_STATE_FILE}"
TRACE_URL="{WARP_TRACE_URL}"
WARP_PROXY="{WARP_PROXY_URL}"

mkdir -p "$STATE_DIR"

read_state() {{
    if [ -f "$STATE_FILE" ]; then
        cat "$STATE_FILE"
    else
        echo "OFF"
    fi
}}

write_state() {{
    printf '%s\\n' "$1" > "$STATE_FILE"
}}

backend_start() {{
    systemctl restart sing-box.service
}}

backend_stop() {{
    systemctl stop sing-box.service >/dev/null 2>&1 || true
}}

backend_active() {{
    systemctl is-active --quiet sing-box.service
}}

firewall_apply() {{
    systemctl start vpn-killswitch.service
}}

firewall_remove() {{
    systemctl stop vpn-killswitch.service >/dev/null 2>&1 || true
}}

firewall_refresh() {{
    systemctl reload vpn-killswitch.service >/dev/null 2>&1 || \\
        systemctl restart vpn-killswitch.service
}}

firewall_active() {{
    nft list table inet vpnks >/dev/null 2>&1
}}

trace_direct() {{
    curl -fsS --connect-timeout 5 --max-time 8 "$TRACE_URL" 2>/dev/null || true
}}

trace_proxy() {{
    curl -fsS --proxy "$WARP_PROXY" --connect-timeout 5 --max-time 8 "$TRACE_URL" 2>/dev/null || true
}}

trace_reports_warp() {{
    grep -Eq 'warp=(on|plus)'
}}

health_warp() {{
    if trace_proxy | trace_reports_warp; then
        return 0
    fi
    if trace_direct | trace_reports_warp; then
        return 0
    fi
    return 1
}}

health_ok() {{
    firewall_active && backend_active && health_warp
}}

collect_health_event() {{
    if health_ok; then
        echo "HEALTH_OK"
    else
        echo "HEALTH_FAIL"
    fi
}}

reduce() {{
    local state="$1"
    local event="$2"

    case "$event" in
        USER_ON)
            echo "CONNECTING:APPLY_FIREWALL START_BACKEND CHECK_HEALTH"
            ;;
        USER_OFF)
            echo "OFF:STOP_BACKEND REMOVE_FIREWALL"
            ;;
        REFRESH)
            echo "$state:REFRESH_FIREWALL"
            ;;
        STATUS)
            echo "$state:CHECK_HEALTH"
            ;;
        HEALTH_OK)
            case "$state" in
                CONNECTING|ON|DEGRADED) echo "ON:" ;;
                *) echo "$state:" ;;
            esac
            ;;
        HEALTH_FAIL)
            case "$state" in
                CONNECTING|ON|DEGRADED) echo "DEGRADED:" ;;
                *) echo "$state:" ;;
            esac
            ;;
        *)
            echo "$state:"
            ;;
    esac
}}

run_actions() {{
    local actions="$1"
    local action health_event transition

    for action in $actions; do
        case "$action" in
            APPLY_FIREWALL) firewall_apply ;;
            REMOVE_FIREWALL) firewall_remove ;;
            START_BACKEND) backend_start ;;
            STOP_BACKEND) backend_stop ;;
            REFRESH_FIREWALL) firewall_refresh ;;
            CHECK_HEALTH)
                health_event="$(collect_health_event)"
                transition="$(reduce "$(read_state)" "$health_event")"
                write_state "${{transition%%:*}}"
                ;;
        esac
    done
}}

dispatch() {{
    local event="$1"
    local transition next_state actions

    transition="$(reduce "$(read_state)" "$event")"
    next_state="${{transition%%:*}}"
    actions="${{transition#*:}}"
    write_state "$next_state"
    run_actions "$actions"
}}

command_on() {{
    dispatch USER_ON
    echo "$(read_state)"
    [ "$(read_state)" = "ON" ]
}}

command_off() {{
    dispatch USER_OFF
    echo "OFF"
}}

command_status() {{
    dispatch STATUS
    echo "$(read_state)"
    [ "$(read_state)" != "DEGRADED" ]
}}

command_refresh() {{
    dispatch REFRESH
    echo "$(read_state)"
}}

case "${{1:-}}" in
    on) command_on ;;
    off) command_off ;;
    status) command_status ;;
    refresh) command_refresh ;;
    *) echo "usage: vpnctl {{on|off|status|refresh}}" >&2; exit 64 ;;
esac
"""


VPNKS_SYSTEMD_UNIT = f"""[Unit]
Description=VPS outbound VPN safety firewall (SSH input untouched)
Documentation=https://github.com/henryliu443/Automated-sing-box-json-generator
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStartPre={VPN_SAFETY_REFRESH_PATH}
ExecStart=/usr/sbin/nft -f {VPNKS_NFT_PATH}
ExecReload={VPN_SAFETY_REFRESH_PATH}
ExecReload=/usr/sbin/nft -f {VPNKS_NFT_PATH}
ExecStop=/bin/sh -c '/usr/sbin/nft delete table inet vpnks 2>/dev/null || true'

[Install]
WantedBy=multi-user.target
"""


def command_exists(name):
    return subprocess.run(
        ["sh", "-c", f"command -v {name} >/dev/null 2>&1"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    ).returncode == 0


def run_cmd(cmd):
    ui.command(cmd)
    subprocess.run(cmd, shell=True, check=True)


def ensure_nftables():
    if command_exists("nft"):
        return
    ui.step("安装 nftables")
    if command_exists("apt-get"):
        run_cmd("DEBIAN_FRONTEND=noninteractive apt-get update")
        run_cmd("DEBIAN_FRONTEND=noninteractive apt-get install -y nftables")
    elif command_exists("dnf"):
        run_cmd("dnf install -y nftables")
    elif command_exists("yum"):
        run_cmd("yum install -y nftables")
    else:
        raise RuntimeError("未检测到可用包管理器，无法安装 nftables")


def _write_file(path, content, mode):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(content).lstrip())
    os.chmod(path, mode)


def deploy_killswitch_assets():
    """Install vpnctl and safety firewall assets without enabling VPN."""
    ensure_nftables()

    ui.step(f"写入安全层刷新脚本: {VPN_SAFETY_REFRESH_PATH}")
    _write_file(VPN_SAFETY_REFRESH_PATH, VPN_SAFETY_REFRESH_SCRIPT, 0o755)

    ui.step(f"写入 VPN 控制面脚本: {VPNCTL_PATH}")
    _write_file(VPNCTL_PATH, VPNCTL_SCRIPT, 0o755)

    ui.step(f"写入 kill switch systemd unit: {VPNKS_SERVICE_UNIT_PATH}")
    _write_file(VPNKS_SERVICE_UNIT_PATH, VPNKS_SYSTEMD_UNIT, 0o644)
    run_cmd("systemctl daemon-reload")

    ui.success(
        "VPN 控制面已安装；SSH input 不受管理。使用 vpnctl on/off/status/refresh 控制。"
    )


def killswitch_status():
    if not os.path.isfile(VPNCTL_PATH):
        return "not-installed"
    result = subprocess.run(
        [VPNCTL_PATH, "status"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return (result.stdout or result.stderr or "unknown").strip()
