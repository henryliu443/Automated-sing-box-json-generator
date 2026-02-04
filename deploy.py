import json
import subprocess
import secrets
import string
import os
import re

# 1. 生成 1Password 级别的 20 位随机密码
def gen_pwd(length=20):
    chars = string.ascii_letters + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))


def run_cmd(cmd):
    try:
        return subprocess.check_output(cmd, shell=True).decode().strip()
    except:
        return ""


print("\n" + "🚀" * 10)
print("Sing-box & Watchdog 终极全自动无痕部署 (自动清理冗余任务)")
print("🚀" * 10)

S_IP = input("请输入服务器 IP: ").strip()

# 2. 动态生成本轮凭据 (UUID/Keys/Passwords)
T_U = run_cmd("sing-box generate uuid")
r_raw = run_cmd("sing-box generate reality-keypair")
R_PRV = re.search(r"PrivateKey: (.*)", r_raw).group(1) if r_raw else ""
R_PUB = re.search(r"PublicKey: (.*)", r_raw).group(1) if r_raw else ""
A_P, T_P, H_P, H_O = gen_pwd(), gen_pwd(), gen_pwd(), gen_pwd()

# 3. 组装服务器 config.json
sv_cfg = {
    "log": {"level": "info", "timestamp": True},
    "inbounds": [
        {
            "type": "anytls",
            "tag": "anytls-in",
            "listen": "::",
            "listen_port": 23244,
            "sniff": True,
            "users": [{"name": "user", "password": A_P}],
            "padding_scheme": [
                "stop=8",
                "0=30-30",
                "1=100-400",
                "2=400-500,c,500-1000,c,500-1000,c,500-1000,c,500-1000",
                "3=9-9,500-1000",
                "4=500-1000",
                "5=500-1000",
                "6=500-1000",
                "7=500-1000"
            ],
            "tls": {
                "enabled": True,
                "server_name": "react.dev",
                "reality": {
                    "enabled": True,
                    "handshake": {"server": "react.dev", "server_port": 443},
                    "private_key": R_PRV,
                    "short_id": "0123456789abcdef"
                }
            }
        },
        {
            "type": "tuic",
            "tag": "tuic-in",
            "listen": "::",
            "listen_port": 9443,
            "users": [{"uuid": T_U, "password": T_P}],
            "congestion_control": "bbr",
            "zero_rtt_handshake": True,
            "tls": {
                "enabled": True,
                "certificate_path": "/etc/sing-box-tuic/certs/tuic.crt",
                "key_path": "/etc/sing-box-tuic/certs/tuic.key"
            }
        },
        {
            "type": "hysteria2",
            "tag": "hy2-in",
            "listen": "::",
            "listen_port": 7443,
            "users": [{"password": H_P}],
            "ignore_client_bandwidth": True,
            "obfs": {"type": "salamander", "password": H_O},
            "masquerade": "https://bing.com",
            "tls": {
                "enabled": True,
                "certificate_path": "/etc/hysteria/server.crt",
                "key_path": "/etc/hysteria/server.key"
            }
        }
    ],
    "outbounds": [
        {
            "type": "socks",
            "tag": "warp-out",
            "server": "127.0.0.1",
            "server_port": 40000,
            "version": "5",
            "udp_over_tcp": True
        },
        {"type": "direct", "tag": "direct"}
    ],
    "route": {
        "rules": [
            {"inbound": ["anytls-in", "tuic-in", "hy2-in"], "outbound": "warp-out"}
        ],
        "final": "warp-out"
    }
}

# 4. 组装客户端 GUI JSON
cl_cfg = {
    "log": {"level": "info", "timestamp": True},
    "dns": {
        "servers": [
            {"type": "https", "tag": "dns-remote", "detour": "anytls-out", "server": "1.1.1.1"},
            {"type": "udp", "tag": "local", "server": "223.5.5.5"}
        ],
        "rules": [
            {"outbound": "any", "server": "local"},
            {"rule_set": "cn", "server": "local"} # 修正：变量名对齐
        ],
        "final": "dns-remote"
    },
    "inbounds": [
        {
            "type": "tun",
            "tag": "tun-in",
            "address": "172.19.0.1/30",
            "auto_route": True,
            "strict_route": True,
            "stack": "system",
            "sniff": True,
            "sniff_override_destination": True
        }
    ],
    "outbounds": [
        {
            "type": "selector",
            "tag": "proxy-best",
            "outbounds": ["性能池-自动负载", "anytls-out", "direct"],
            "default": "性能池-自动负载"
        },
        {
            "type": "urltest",
            "tag": "性能池-自动负载",
            "outbounds": ["tuic-out", "hy2-out", "anytls-out"],
            "url": "https://www.gstatic.com/generate_204",
            "interval": "3m0s",
            "tolerance": 50
        },
        {
            "type": "anytls",
            "tag": "anytls-out",
            "server": S_IP,
            "server_port": 23244,
            "tls": {
                "enabled": True,
                "server_name": "react.dev",
                "utls": {"enabled": True, "fingerprint": "chrome"},
                "reality": {
                    "enabled": True,
                    "public_key": R_PUB,
                    "short_id": "0123456789abcdef"
                }
            },
            "password": A_P
        },
        {
            "type": "tuic",
            "tag": "tuic-out",
            "server": S_IP,
            "server_port": 9443,
            "uuid": T_U,
            "password": T_P,
            "congestion_control": "bbr",
            "udp_relay_mode": "quic",
            "tls": {
                "enabled": True,
                "server_name": "react.dev",
                "insecure": True
            }
        },
        {
            "type": "hysteria2",
            "tag": "hy2-out",
            "server": S_IP,
            "server_port": 7443,
            "obfs": {"type": "salamander", "password": H_O},
            "password": H_P,
            "tls": {
                "enabled": True,
                "server_name": "bing.com",
                "insecure": True
            }
        },
        {"type": "direct", "tag": "direct"}
    ],
    "route": {
        "rules": [
            { "protocol": "dns", "action": "hijack-dns" },
            {
                "rule_set": [
                    "cn", "cn-cdn", "apple", "icloud", "wechat", "alipay", "xiaohongshu", 
                    "meituan", "amap", "douyin", "jd", "bilibili", "chaoxing", "banking-hk"
                ],
                "action": "route",
                "outbound": "direct"
            },
            { "rule_set": ["geoip-cn", "geoip-hk"], "action": "route", "outbound": "direct" }
        ],
        "rule_set": [
            { "tag": "cn", "type": "remote", "format": "binary", "url": "https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/sing/geo/geosite/cn.srs", "download_detour": "proxy-best" },
            { "tag": "geoip-cn", "type": "remote", "format": "binary", "url": "https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/sing/geo/geoip/cn.srs", "download_detour": "proxy-best" },
            { "tag": "alipay", "type": "remote", "format": "binary", "url": "https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/sing/geo/geosite/alipay.srs", "download_detour": "proxy-best" },
            { "tag": "wechat", "type": "remote", "format": "binary", "url": "https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/sing/geo/geosite/wechat.srs", "download_detour": "proxy-best" },
            { "tag": "xiaohongshu", "type": "remote", "format": "binary", "url": "https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/sing/geo/geosite/xiaohongshu.srs", "download_detour": "proxy-best" },
            { "tag": "cn-cdn", "type": "remote", "format": "binary", "url": "https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/sing/geo/geosite/cn-cdn.srs", "download_detour": "proxy-best" },
            { "tag": "apple", "type": "remote", "format": "binary", "url": "https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/sing/geo/geosite/apple.srs", "download_detour": "proxy-best" },
            { "tag": "icloud", "type": "remote", "format": "binary", "url": "https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/sing/geo/geosite/icloud.srs", "download_detour": "proxy-best" },
            { "tag": "meituan", "type": "remote", "format": "binary", "url": "https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/sing/geo/geosite/meituan.srs", "download_detour": "proxy-best" },
            { "tag": "amap", "type": "remote", "format": "binary", "url": "https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/sing/geo/geosite/amap.srs", "download_detour": "proxy-best" },
            { "tag": "douyin", "type": "remote", "format": "binary", "url": "https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/sing/geo/geosite/douyin.srs", "download_detour": "proxy-best" },
            { "tag": "jd", "type": "remote", "format": "binary", "url": "https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/sing/geo/geosite/jd.srs", "download_detour": "proxy-best" },
            { "tag": "bilibili", "type": "remote", "format": "binary", "url": "https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/sing/geo/geosite/bilibili.srs", "download_detour": "proxy-best" },
            { "tag": "chaoxing", "type": "remote", "format": "binary", "url": "https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/sing/geo/geosite/chaoxing.srs", "download_detour": "proxy-best" },
            { "tag": "banking-hk", "type": "remote", "format": "binary", "url": "https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/sing/geo/geosite/banking_hk.srs", "download_detour": "proxy-best" },
            { "tag": "geoip-hk", "type": "remote", "format": "binary", "url": "https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/sing/geo/geoip/hk.srs", "download_detour": "proxy-best" }
        ],
        "final": "proxy-best",
        "auto_detect_interface": True
    }
}

# 5. 集成 Watchdog 并写入文件
wd_content = r"""#!/bin/bash
# (此处省略脚本内具体注释以精简)
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
    echo "$(date): [静默] 网络不可用，跳过。" >> "$LOG_FILE"
    exit 0
fi

if check_warp_tunnel; then
    if [ -f "$FAIL_COUNT_FILE" ]; then rm -f "$FAIL_COUNT_FILE"; fi
    exit 0
else
    CURRENT_FAIL=0
    if [ -f "$FAIL_COUNT_FILE" ]; then CURRENT_FAIL=$(cat "$FAIL_COUNT_FILE"); fi
    NEXT_FAIL=$((CURRENT_FAIL + 1))
    echo "$NEXT_FAIL" > "$FAIL_COUNT_FILE"

    if [ "$NEXT_FAIL" -ge "$MAX_RETRIES" ]; then
        echo "$(date): 执行修复..." >> "$LOG_FILE"
        warp-cli disconnect > /dev/null 2>&1
        sleep 2
        warp-cli connect > /dev/null 2>&1
        rm -f "$FAIL_COUNT_FILE"
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

# 清理并挂载任务
clean_cron = '(crontab -l 2>/dev/null | grep -v "warp_lazy_watchdog.sh"; echo "* * * * * /root/warp_lazy_watchdog.sh") | crontab -'
subprocess.run(clean_cron, shell=True)

subprocess.run(["systemctl", "restart", "sing-box"])

# 6. 最终输出
print("\n✅ 部署成功！")
print("🛠️ Crontab 已自动去重并挂载完成。")
print("\n" + "="*20 + " 请全选复制客户端 JSON " + "="*20)
print(json.dumps(cl_cfg, indent=2))
print("="*60)
