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
            {"rule_set": "geosite-cn", "server": "local"}
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
        "rules": [{"protocol": "dns", "action": "hijack-dns"}],
        "rule_set": [
            {
                "type": "remote",
                "tag": "geosite-cn",
                "url": "https://fastly.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@sing/geo/geosite/cn.srs",
                "format": "binary"
            },
            {
                "type": "remote",
                "tag": "geoip-cn",
                "url": "https://fastly.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@sing/geo/geoip/cn.srs",
                "format": "binary"
            }
        ],
        "final": "proxy-best",
        "auto_detect_interface": True
    }
}

# 5. 集成 Watchdog 并写入文件
wd_content = """#!/bin/bash
if ! ping -c 2 -W 2 8.8.8.8 > /dev/null 2>&1; then exit 0; fi
if ! curl -s --proxy socks5h://127.0.0.1:40000 --max-time 5 https://www.cloudflare.com/cdn-cgi/trace | grep -q "colo="; then
    warp-cli disconnect && sleep 2 && warp-cli connect
fi
"""

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

# 6. 最终输出
print("\n✅ 部署成功！")
print("🛠️  Crontab 已自动去重并挂载完成。")
print("\n" + "="*20 + " 请全选复制客户端 JSON " + "="*20)
print(json.dumps(cl_cfg, indent=2))
print("="*60 + "\n⚠️ 提示：配置信息仅显示一次，且密码已随机更新！")
