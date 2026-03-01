from credentials import A_P, R_PRV, R_PUB, T_U, T_P, H_P, H_O, S_IP

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
        "rules": [
            # 1. 拦截 DNS 流量
            {"protocol": "dns", "action": "hijack-dns"},
            
            # 2. 绕过私有网络 (局域网/回环)
            {
                "ip_is_private": True,
                "outbound": "direct"
            },
            
            # 3. 绕过国内域名 (基于 geosite-cn)
            {
                "rule_set": "geosite-cn",
                "outbound": "direct"
            },
            
            # 4. 绕过国内 IP (基于 geoip-cn)
            {
                "rule_set": "geoip-cn",
                "outbound": "direct"
            }
        ],
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