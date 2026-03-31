from route_profile import TUN_EXCLUDED_ROUTES, build_dns_config, build_route_config


REALITY_DECOY_SERVER = "react.dev"

REALITY_DECOY_PORT = 443

HY2_MASQUERADE_URL = "https://www.cloudflare.com"

TUIC_CERT_PATH = "/etc/sing-box-tuic/certs/tuic.crt"

TUIC_KEY_PATH = "/etc/sing-box-tuic/certs/tuic.key"

HY2_CERT_PATH = "/etc/hysteria/server.crt"

HY2_KEY_PATH = "/etc/hysteria/server.key"

# SNI segmented domain mapping:
# jx1xfnke -> reality, t7mmubf0 -> hy2, xts6e4iz -> tuic
def build_protocol_hosts(domain_root):
    if not domain_root or not domain_root.strip():
        raise ValueError("domain_root is required")

    root = domain_root.strip().lower().rstrip(".")

    return {

        "reality": f"jx1xfnke.{root}",

        "hy2": f"t7mmubf0.{root}",

        "tuic": f"xts6e4iz.{root}",

    }


def build_server_outbounds(warp_mode):
    if warp_mode == "proxy":
        return [
            {
                "type": "socks",
                "tag": "warp-out",
                "server": "127.0.0.1",
                "server_port": 40000,
                "version": "5",
                "udp_over_tcp": True,
            },
            {"type": "direct", "tag": "direct"},
        ]

    if warp_mode == "tun":
        return [
            # When the host itself is connected to WARP, regular direct traffic
            # will be routed through the system tunnel by the OS.
            {"type": "direct", "tag": "warp-out"},
            {"type": "direct", "tag": "direct"},
        ]

    raise ValueError(f"unsupported warp_mode: {warp_mode}")


def build_server_config(creds, protocol_hosts=None, warp_mode="proxy"):
    if not protocol_hosts:
        raise ValueError("protocol_hosts is required")
    hosts = protocol_hosts

    return {

        "log": {"disabled": True},

        "inbounds": [

            {

                "type": "anytls",

                "tag": "anytls-in",

                "listen": "::",

                "listen_port": 23244,

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

                    "server_name": REALITY_DECOY_SERVER,  # ← 修复：改为伪装域名 react.dev

                    "reality": {

                        "enabled": True,

                        "handshake": {

                            "server": REALITY_DECOY_SERVER,

                            "server_port": REALITY_DECOY_PORT,

                        },

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

                    "server_name": hosts["tuic"],

                    "certificate_path": TUIC_CERT_PATH,

                    "key_path": TUIC_KEY_PATH,

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

                "masquerade": HY2_MASQUERADE_URL,

                "tls": {

                    "enabled": True,

                    "server_name": hosts["hy2"],

                    "certificate_path": HY2_CERT_PATH,

                    "key_path": HY2_KEY_PATH,

                },

            },

        ],

        "outbounds": build_server_outbounds(warp_mode),

        "route": {

            "rules": [
                {
                    "inbound": ["anytls-in", "tuic-in", "hy2-in"],
                    "action": "route",
                    "outbound": "warp-out",
                }
            ],

            "final": "warp-out",

        },

    }


def build_client_config(creds, protocol_hosts=None):
    if not protocol_hosts:
        raise ValueError("protocol_hosts is required")
    hosts = protocol_hosts

    return {

        "log": {"disabled": True},

        "dns": build_dns_config(hosts),

        "inbounds": [

            {

                "type": "tun",

                "tag": "tun-in",

                "address": "172.19.0.1/30",

                "auto_route": True,

                "strict_route": True,

                "route_exclude_address": TUN_EXCLUDED_ROUTES,

                "stack": "system",

            }

        ],

        "outbounds": [

            {

                "type": "urltest",

                "tag": "proxy-best",

                "outbounds": ["tuic-out", "hy2-out", "anytls-out"],

                "url": "https://cp.cloudflare.com/generate_204",

                "interval": "10m",

                "tolerance": 50,

            },

            {

                "type": "anytls",

                "tag": "anytls-out",

                "server": hosts["reality"],

                "domain_resolver": "dns-direct",

                "server_port": 23244,

                "tls": {
                    "enabled": True,
                    "server_name": REALITY_DECOY_SERVER,
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

                "server": hosts["tuic"],

                "domain_resolver": "dns-direct",

                "server_port": 9443,

                "uuid": creds["uuid"],

                "password": creds["pwd_tuic"],

                "congestion_control": "bbr",

                "udp_relay_mode": "quic",

                "tls": {

                    "enabled": True,

                    "server_name": hosts["tuic"],

                },

            },

            {

                "type": "hysteria2",

                "tag": "hy2-out",

                "server": hosts["hy2"],

                "domain_resolver": "dns-direct",

                "server_port": 7443,

                "obfs": {"type": "salamander", "password": creds["pwd_obfs"]},

                "password": creds["pwd_hy2"],

                "tls": {

                    "enabled": True,

                    "server_name": hosts["hy2"],

                },

            },

            {"type": "direct", "tag": "direct"},

        ],

        "route": build_route_config(),

    }
