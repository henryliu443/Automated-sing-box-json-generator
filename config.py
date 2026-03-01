def build_server_config(creds):
    return {
        "log": {"level": "info", "timestamp": True},
        "inbounds": [
            {
                "type": "anytls",
                "tag": "anytls-in",
                "listen": "::",
                "listen_port": 23244,
                "sniff": True,
                "users": [{"name": "user", "password": creds["pwd_anytls"]}],
                "padding_scheme": [
                    "stop=8",
                    "0=30-30",
                    "1=100-400",
                    "2=400-500,c,500-1000,c,500-1000,c,500-1000,c,500-1000",
                    "3=9-9,500-1000",
                    "4=500-1000",
                    "5=500-1000",
                    "6=500-1000",
                    "7=500-1000",
                ],
                "tls": {
                    "enabled": True,
                    "server_name": "react.dev",
                    "reality": {
                        "enabled": True,
                        "handshake": {"server": "react.dev", "server_port": 443},
                        "private_key": creds["private_key"],
                        "short_id": "0123456789abcdef",
                    },
                },
            },
            {
                "type": "tuic",
                "tag": "tuic-in",
                "listen": "::",
                "listen_port": 9443,
                "users": [{"uuid": creds["uuid"], "password": creds["pwd_tuic"]}],
                "congestion_control": "bbr",
                "zero_rtt_handshake": True,
                "tls": {
                    "enabled": True,
                    "certificate_path": "/etc/sing-box-tuic/certs/tuic.crt",
                    "key_path": "/etc/sing-box-tuic/certs/tuic.key",
                },
            },
            {
                "type": "hysteria2",
                "tag": "hy2-in",
                "listen": "::",
                "listen_port": 7443,
                "users": [{"password": creds["pwd_hy2"]}],
                "ignore_client_bandwidth": True,
                "obfs": {"type": "salamander", "password": creds["pwd_obfs"]},
                "masquerade": "https://bing.com",
                "tls": {
                    "enabled": True,
                    "certificate_path": "/etc/hysteria/server.crt",
                    "key_path": "/etc/hysteria/server.key",
                },
            },
        ],
        "outbounds": [
            {
                "type": "socks",
                "tag": "warp-out",
                "server": "127.0.0.1",
                "server_port": 40000,
                "version": "5",
                "udp_over_tcp": True,
            },
            {"type": "direct", "tag": "direct"},
        ],
        "route": {
            "rules": [{"inbound": ["anytls-in", "tuic-in", "hy2-in"], "outbound": "warp-out"}],
            "final": "warp-out",
        },
    }


def build_client_config(creds, server_ip):
    return {
        "log": {"level": "info", "timestamp": True},
        "dns": {
            "servers": [
                {
                    "tag": "dns-remote",
                    "address": "https://8.8.8.8/dns-query",
                    "detour": "proxy-best",
                },
                {
                    "tag": "dns-direct",
                    "address": "https://223.5.5.5/dns-query",
                },
                {
                    "tag": "dns-block",
                    "address": "rcode://success",
                },
            ],
            "rules": [
                {"outbound": "any", "server": "dns-direct"},
                {"rule_set": "geosite-category-ads-all", "server": "dns-block"},
                {"rule_set": ["geosite-apple-cn", "geosite-cn"], "server": "dns-direct"},
                {"rule_set": "geosite-geolocation-!cn", "server": "dns-remote"},
            ],
            "final": "dns-remote",
            "strategy": "prefer_ipv4",
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
                "sniff_override_destination": True,
            }
        ],
        "outbounds": [
            {
                "type": "selector",
                "tag": "proxy-best",
                "outbounds": ["性能池-自动负载", "anytls-out", "direct"],
                "default": "性能池-自动负载",
            },
            {
                "type": "urltest",
                "tag": "性能池-自动负载",
                "outbounds": ["tuic-out", "hy2-out", "anytls-out"],
                "url": "https://www.gstatic.com/generate_204",
                "interval": "3m0s",
                "tolerance": 50,
            },
            {
                "type": "anytls",
                "tag": "anytls-out",
                "server": server_ip,
                "server_port": 23244,
                "tls": {
                    "enabled": True,
                    "server_name": "react.dev",
                    "utls": {"enabled": True, "fingerprint": "chrome"},
                    "reality": {
                        "enabled": True,
                        "public_key": creds["public_key"],
                        "short_id": "0123456789abcdef",
                    },
                },
                "password": creds["pwd_anytls"],
            },
            {
                "type": "tuic",
                "tag": "tuic-out",
                "server": server_ip,
                "server_port": 9443,
                "uuid": creds["uuid"],
                "password": creds["pwd_tuic"],
                "congestion_control": "bbr",
                "udp_relay_mode": "quic",
                "tls": {"enabled": True, "server_name": "react.dev", "insecure": True},
            },
            {
                "type": "hysteria2",
                "tag": "hy2-out",
                "server": server_ip,
                "server_port": 7443,
                "obfs": {"type": "salamander", "password": creds["pwd_obfs"]},
                "password": creds["pwd_hy2"],
                "tls": {"enabled": True, "server_name": "bing.com", "insecure": True},
            },
            {"type": "direct", "tag": "direct"},
        ],
        "route": {
            "rules": [
                {"protocol": "dns", "action": "hijack-dns"},
                {"rule_set": "geosite-category-ads-all", "action": "reject"},
                {"ip_is_private": True, "outbound": "direct"},
                {"rule_set": ["geosite-apple-cn", "geosite-cn", "geoip-cn"], "outbound": "direct"},
                {"rule_set": "geosite-geolocation-!cn", "outbound": "proxy-best"},
            ],
            "rule_set": [
                {
                    "type": "remote",
                    "tag": "geosite-apple-cn",
                    "url": "https://fastly.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@sing/geo/geosite/apple-cn.srs",
                    "format": "binary",
                },
                {
                    "type": "remote",
                    "tag": "geosite-cn",
                    "url": "https://fastly.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@sing/geo/geosite/cn.srs",
                    "format": "binary",
                },
                {
                    "type": "remote",
                    "tag": "geosite-geolocation-!cn",
                    "url": "https://fastly.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@sing/geo/geosite/geolocation-!cn.srs",
                    "format": "binary",
                },
                {
                    "type": "remote",
                    "tag": "geoip-cn",
                    "url": "https://fastly.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@sing/geo/geoip/cn.srs",
                    "format": "binary",
                },
                {
                    "type": "remote",
                    "tag": "geosite-category-ads-all",
                    "url": "https://fastly.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@sing/geo/geosite/category-ads-all.srs",
                    "format": "binary",
                },
            ],
            "final": "proxy-best",
            "auto_detect_interface": True,
        },
    }
