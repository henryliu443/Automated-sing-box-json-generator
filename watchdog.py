import os
import subprocess

WATCHDOG_SCRIPT = r"""#!/bin/bash

# --- 配置区 ---
LOCK_FILE="/var/run/warp_watchdog.lock"
FAIL_COUNT_FILE="/var/run/warp_fail_count"
LOG_FILE="/var/log/warp_monitor.log"

MAX_RETRIES=2
WARP_PROXY="socks5h://127.0.0.1:40000"
CHECK_URL="https://www.cloudflare.com/cdn-cgi/trace"

exec 9>"$LOCK_FILE"
flock -n 9 || exit 0

check_native_net() {
    ping -c 2 -W 2 8.8.8.8 > /dev/null 2>&1
}

check_warp_tunnel() {
    curl -s --proxy "$WARP_PROXY" --max-time 5 "$CHECK_URL" | grep -q "colo="
}

if ! check_native_net; then
    echo "$(date): [静默] 本地网络无法连通 8.8.8.8，跳过 WARP 检测。" >> "$LOG_FILE"
    exit 0
fi

if check_warp_tunnel; then
    if [ -f "$FAIL_COUNT_FILE" ]; then
        rm -f "$FAIL_COUNT_FILE"
        echo "$(date): [恢复] WARP 链路已恢复。" >> "$LOG_FILE"
    fi
    exit 0
fi

CURRENT_FAIL=0
if [ -f "$FAIL_COUNT_FILE" ]; then
    CURRENT_FAIL=$(cat "$FAIL_COUNT_FILE")
fi

NEXT_FAIL=$((CURRENT_FAIL + 1))
echo "$NEXT_FAIL" > "$FAIL_COUNT_FILE"

if [ "$NEXT_FAIL" -ge "$MAX_RETRIES" ]; then
    echo "$(date): [动作] 连续失败 $NEXT_FAIL 次，执行修复..." >> "$LOG_FILE"
    warp-cli disconnect > /dev/null 2>&1
    sleep 2
    warp-cli connect > /dev/null 2>&1
    rm -f "$FAIL_COUNT_FILE"
else
    echo "$(date): [观察] WARP 探测失败 (第 $NEXT_FAIL 次)，暂不操作。" >> "$LOG_FILE"
fi
"""


def deploy_watchdog(script_path="/root/warp_lazy_watchdog.sh"):
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(WATCHDOG_SCRIPT)
    os.chmod(script_path, 0o755)

    cron_line = f"* * * * * {script_path}"
    clean_cron = f'(crontab -l 2>/dev/null | grep -v "{script_path}"; echo "{cron_line}") | crontab -'
    subprocess.run(clean_cron, shell=True, check=True)


if __name__ == "__main__":
    deploy_watchdog()
    print("Watchdog 已部署并挂载 crontab。")
