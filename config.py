from route_profile import TUN_EXCLUDED_ROUTES, build_dns_config, build_route_config


REALITY_DECOY_SERVER = "react.dev"
ANYTLS_INBOUND_TAG = "anytls-in"
TUIC_INBOUND_TAG = "tuic-in"
HY2_INBOUND_TAG = "hy2-in"
CLIENT_TUN_INBOUND_TAG = "tun-in"
CLIENT_PROXY_BEST_TAG = "proxy-best"
CLIENT_PROXY_AUTO_TAG = "proxy-auto"
CLIENT_PROXY_OUTBOUND_TAGS = ["tuic-out", "hy2-out", "anytls-out"]

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


def build_domain_resolver(server_tag="dns-direct"):
    return {
        "server": server_tag,
        "strategy": "prefer_ipv4",
    }


def build_client_outbounds(creds, hosts):
    return [
        {
            "type": "selector",
            "tag": CLIENT_PROXY_BEST_TAG,
            "outbounds": [CLIENT_PROXY_AUTO_TAG, *CLIENT_PROXY_OUTBOUND_TAGS, "direct"],
            "default": CLIENT_PROXY_AUTO_TAG,
            "interrupt_exist_connections": True,
        },
        {
            "type": "urltest",
            "tag": CLIENT_PROXY_AUTO_TAG,
            "outbounds": CLIENT_PROXY_OUTBOUND_TAGS,
            "url": "https://cp.cloudflare.com/generate_204",
            "interval": "10m",
            "tolerance": 50,
        },
        {
            "type": "anytls",
            "tag": "anytls-out",
            "server": hosts["reality"],
            "domain_resolver": build_domain_resolver(),
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
            "domain_resolver": build_domain_resolver(),
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
            "domain_resolver": build_domain_resolver(),
            "server_port": 7443,
            "obfs": {"type": "salamander", "password": creds["pwd_obfs"]},
            "password": creds["pwd_hy2"],
            "tls": {
                "enabled": True,
                "server_name": hosts["hy2"],
            },
        },
        {"type": "direct", "tag": "direct"},
    ]


def build_server_config(creds, protocol_hosts=None, warp_mode="proxy"):
    if not protocol_hosts:
        raise ValueError("protocol_hosts is required")
    hosts = protocol_hosts

    return {

        "log": {"disabled": True},

        "inbounds": [

            {

                "type": "anytls",

                "tag": ANYTLS_INBOUND_TAG,

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

                "tag": TUIC_INBOUND_TAG,

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

                "tag": HY2_INBOUND_TAG,

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
                    "inbound": ANYTLS_INBOUND_TAG,
                    "action": "resolve",
                    "strategy": "prefer_ipv4",
                },
                {
                    "inbound": ANYTLS_INBOUND_TAG,
                    "action": "sniff",
                    "timeout": "1s",
                },
                {
                    "inbound": [ANYTLS_INBOUND_TAG, TUIC_INBOUND_TAG, HY2_INBOUND_TAG],
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

        "log": {
            "level": "debug",
            "timestamp": True,
        },

        "dns": build_dns_config(hosts),

        "inbounds": [

            {

                "type": "tun",

                "tag": CLIENT_TUN_INBOUND_TAG,

                "address": "172.19.0.1/30",

                "auto_route": True,

                "strict_route": True,

                "route_exclude_address": TUN_EXCLUDED_ROUTES,

                "stack": "system",

            }

        ],

        "outbounds": build_client_outbounds(creds, hosts),

        "route": build_route_config(sniff_inbound=CLIENT_TUN_INBOUND_TAG),

    }
