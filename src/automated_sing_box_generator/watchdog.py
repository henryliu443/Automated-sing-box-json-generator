import os
import subprocess
from pathlib import Path


_TEMPLATE_DIR = Path(__file__).parent / "templates"
_WATCHDOG_TEMPLATE = _TEMPLATE_DIR / "warp_watchdog.sh.template"

_WARP_CHECK_PROXY = """\
check_warp_data_plane() {
    if ! tcp_connect "$WARP_PROXY_HOST" "$WARP_PROXY_PORT" "$PROXY_CONNECT_TIMEOUT"; then
        return 1
    fi

    timeout "$WARP_CHECK_TIMEOUT" curl -fsS --proxy "$WARP_PROXY" \\
        --connect-timeout "$PROXY_CONNECT_TIMEOUT" \\
        --max-time "$WARP_CHECK_TIMEOUT" \\
        "$WARP_TRACE_URL" 2>/dev/null | grep -Eq 'warp=(on|plus)'
}
"""

_WARP_CHECK_TUN = """\
check_warp_data_plane() {
    timeout "$WARP_CHECK_TIMEOUT" curl -fsS \\
        --connect-timeout "$PROXY_CONNECT_TIMEOUT" \\
        --max-time "$WARP_CHECK_TIMEOUT" \\
        "$WARP_TRACE_URL" 2>/dev/null | grep -Eq 'warp=(on|plus)'
}
"""


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


def deploy_watchdog(script_path="/root/warp_lazy_watchdog.sh", warp_mode="proxy"):
    if warp_mode == "none":
        return
    script_content = build_watchdog_script(warp_mode)
    if script_content is None:
        return
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script_content)
    os.chmod(script_path, 0o755)

    cron_line = f"* * * * * {script_path}"
    clean_cron = f'(crontab -l 2>/dev/null | grep -v "{script_path}"; echo "{cron_line}") | crontab -'
    subprocess.run(clean_cron, shell=True, check=True)
