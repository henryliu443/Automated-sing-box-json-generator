import os
import json
import subprocess

# 5. 集成 Watchdog 并写入文件
wd_content = r"""#!/bin/bash

# --- 配置区 ---
LOCK_FILE="/var/run/warp_watchdog.lock"
FAIL_COUNT_FILE="/var/run/warp_fail_count"
LOG_FILE="/var/log/warp_monitor.log"

# 阈值：连续失败几次才动手？(建议 2 或 3)
MAX_RETRIES=2

# WARP 代理地址
WARP_PROXY="socks5h://127.0.0.1:40000"
# 检测目标：Cloudflare Trace
CHECK_URL="https://www.cloudflare.com/cdn-cgi/trace"

# 解决并发锁
exec 9>"$LOCK_FILE"
flock -n 9 || exit 0

# --- 核心函数 ---

# 1. 基础网络检测
check_native_net() {
    ping -c 2 -W 2 8.8.8.8 > /dev/null 2>&1
}

# 2. WARP 深度检测
check_warp_tunnel() {
    curl -s --proxy "$WARP_PROXY" --max-time 5 "$CHECK_URL" | grep -q "colo="
}

# --- 逻辑主流程 ---

if ! check_native_net; then
    echo "$(date): [静默] 本地网络 (LA) 无法连通 8.8.8.8跳过 WARP 检测。" >> "$LOG_FILE"
    exit 0
fi

if check_warp_tunnel; then
    if [ -f "$FAIL_COUNT_FILE" ]; then
        rm -f "$FAIL_COUNT_FILE"
        echo "$(date): [恢复] WARP 链路已自动恢复 / 保持正常。" >> "$LOG_FILE"
    fi
    exit 0
else
    CURRENT_FAIL=0
    if [ -f "$FAIL_COUNT_FILE" ]; then
        CURRENT_FAIL=$(cat "$FAIL_COUNT_FILE")
    fi
    
    NEXT_FAIL=$((CURRENT_FAIL + 1))
    echo "$NEXT_FAIL" > "$FAIL_COUNT_FILE"

    if [ "$NEXT_FAIL" -ge "$MAX_RETRIES" ]; then
        echo "$(date): [动作] 连续失败 $NEXT_FAIL 次 (超过阈值)，执行修复..." >> "$LOG_FILE"
        
        warp-cli disconnect > /dev/null 2>&1
        sleep 2
        warp-cli connect > /dev/null 2>&1
        
        rm -f "$FAIL_COUNT_FILE"
    else
        echo "$(date): [观察] WARP 探测失败 (第 $NEXT_FAIL 次)，暂不操作。" >> "$LOG_FILE"
    fi
fi
"""

# 执行部署
os.makedirs("/etc/sing-box", exist_ok=True)
with open("/etc/sing-box/config.json", "w") as f:
    json.dump(sv_cfg, f, indent=2)

with open("/root/warp_lazy_watchdog.sh", "w") as f:
    f.write(wd_content)
os.chmod("/root/warp_lazy_watchdog.sh", 0o755)

# --- 🚀 核心改进：清理重复 crontab 任务 ---
print("正在清理旧任务并重新挂载 Watchdog...")
clean_cron = '(crontab -l 2>/dev/null | grep -v "warp_lazy_watchdog.sh"; echo "* * * * * /root/warp_lazy_watchdog.sh") | crontab -'
subprocess.run(clean_cron, shell=True)

subprocess.run(["systemctl", "restart", "sing-box"])
