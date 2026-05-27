import os

from .route_profile import TUN_EXCLUDED_ROUTES, build_dns_config, build_route_config


REALITY_SERVER_ENV = "REALITY_SERVER"
REALITY_PORT_ENV = "REALITY_PORT"
HY2_MASQUERADE_ENV = "HY2_MASQUERADE"
HY2_UP_MBPS_ENV = "HY2_UP_MBPS"
HY2_DOWN_MBPS_ENV = "HY2_DOWN_MBPS"

HY2_CLIENT_UP_MBPS_DEFAULT = 50
HY2_CLIENT_DOWN_MBPS_DEFAULT = 200
HY2_SERVER_UP_MBPS_DEFAULT = 500
HY2_SERVER_DOWN_MBPS_DEFAULT = 500

TUIC_CERT_PATH = "/etc/sing-box-tuic/certs/tuic.crt"
TUIC_KEY_PATH = "/etc/sing-box-tuic/certs/tuic.key"
HY2_CERT_PATH = "/etc/hysteria/server.crt"
HY2_KEY_PATH = "/etc/hysteria/server.key"

CLIENT_TUN_INBOUND_TAG = "tun-in"
CLIENT_PROXY_BEST_TAG = "global"
CLIENT_PROXY_AUTO_TAG = "proxy-auto"
CLIENT_ROUTE_MODE_TAG = "route-mode"
CLIENT_ROUTE_TAG = "route"
URLTEST_URL = "https://cp.cloudflare.com/generate_204"
CLIENT_TUN_STACK = "gvisor"
CLIENT_TUN_ADDRESSES = [
    "172.19.0.1/30",
    "fdfe:dcba:9876::1/126",
]


def _client_tun_route_exclude(server_ip=None):
    """TUN exclusions: private ranges plus our VPS so proxy dials are not captured by TUN."""
    routes = list(TUN_EXCLUDED_ROUTES)
    if not server_ip:
        return routes
    ip = str(server_ip).strip()
    if not ip:
        return routes
    routes.append(f"{ip}/128" if ":" in ip else f"{ip}/32")
    return routes


SERVER_DNS_SERVERS = ("1.1.1.1", "1.0.0.1")
SERVER_DNS_TAG = "dns-server"


def get_reality_decoy_server(opts=None):
    opts = opts or {}
    if opts.get(REALITY_SERVER_ENV):
        return str(opts[REALITY_SERVER_ENV]).strip()
    return os.getenv(REALITY_SERVER_ENV, "www.cloudflare.com").strip() or "www.cloudflare.com"


def get_reality_decoy_port(opts=None):
    opts = opts or {}
    if opts.get(REALITY_PORT_ENV):
        raw = str(opts[REALITY_PORT_ENV]).strip()
    else:
        raw = os.getenv(REALITY_PORT_ENV, "443").strip()
    try:
        return int(raw)
    except ValueError:
        return 443


def get_hy2_masquerade_url(opts=None):
    opts = opts or {}
    if opts.get(HY2_MASQUERADE_ENV):
        return str(opts[HY2_MASQUERADE_ENV]).strip()
    return os.getenv(HY2_MASQUERADE_ENV, "https://www.cloudflare.com").strip() or "https://www.cloudflare.com"


def get_hy2_up_mbps(opts=None, server=False):
    opts = opts or {}
    default = HY2_SERVER_UP_MBPS_DEFAULT if server else HY2_CLIENT_UP_MBPS_DEFAULT
    raw = opts.get(HY2_UP_MBPS_ENV) or os.getenv(HY2_UP_MBPS_ENV, "")
    raw = str(raw).strip()
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    return default


def get_hy2_down_mbps(opts=None, server=False):
    opts = opts or {}
    default = HY2_SERVER_DOWN_MBPS_DEFAULT if server else HY2_CLIENT_DOWN_MBPS_DEFAULT
    raw = opts.get(HY2_DOWN_MBPS_ENV) or os.getenv(HY2_DOWN_MBPS_ENV, "")
    raw = str(raw).strip()
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    return default


PROTOCOL_DEFS = {
    "anytls": {
        "label": "AnyTLS (Reality)",
        "server_port": 23244,
        "transport": "tcp",
        "needs_tls_cert": False,
        "inbound_tag": "anytls-in",
        "outbound_tag": "anytls-out",
        "host_key": "reality",
    },
    "tuic": {
        "label": "TUIC",
        "server_port": 9443,
        "transport": "udp",
        "needs_tls_cert": True,
        "cert_path": TUIC_CERT_PATH,
        "key_path": TUIC_KEY_PATH,
        "inbound_tag": "tuic-in",
        "outbound_tag": "tuic-out",
        "host_key": "tuic",
    },
    "hy2": {
        "label": "Hysteria2",
        "server_port": 7443,
        "transport": "udp",
        "needs_tls_cert": True,
        "cert_path": HY2_CERT_PATH,
        "key_path": HY2_KEY_PATH,
        "inbound_tag": "hy2-in",
        "outbound_tag": "hy2-out",
        "host_key": "hy2",
    },
}

ALL_PROTOCOLS = list(PROTOCOL_DEFS)


def build_protocol_hosts(domain_root, prefixes):
    """Build ``{host_key: fqdn}`` from *domain_root* and random *prefixes*.

    *prefixes* must be ``{"reality": "<hex>", "hy2": "<hex>", "tuic": "<hex>"}``.
    Prefixes are generated per-deployment and stored in state — never
    hard-coded in the public repository.
    """
    if not domain_root or not domain_root.strip():
        raise ValueError("domain_root is required")
    if not prefixes:
        raise ValueError("prefixes is required (random subdomain prefixes)")

    root = domain_root.strip().lower().rstrip(".")
    return {key: f"{prefix}.{root}" for key, prefix in prefixes.items()}


def build_server_outbounds(warp_mode):
    if warp_mode == "proxy":
        return [
            {
                "type": "socks",
                "tag": "warp-out",
                "server": "127.0.0.1",
                "server_port": 40000,
                "version": "5",
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

    if warp_mode == "none":
        return [{"type": "direct", "tag": "direct"}]

    raise ValueError(f"unsupported warp_mode: {warp_mode}")


def build_domain_resolver(server_tag="dns-direct"):
    return {
        "server": server_tag,
        "strategy": "prefer_ipv4",
    }


# ---------------------------------------------------------------------------
# Server inbound builders (one per protocol)
# ---------------------------------------------------------------------------

def _build_anytls_server_inbound(creds, hosts, opts=None):
    decoy_server = get_reality_decoy_server(opts)
    decoy_port = get_reality_decoy_port(opts)
    return {
        "type": "anytls",
        "tag": PROTOCOL_DEFS["anytls"]["inbound_tag"],
        "listen": "::",
        "listen_port": PROTOCOL_DEFS["anytls"]["server_port"],
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
            "server_name": decoy_server,
            "reality": {
                "enabled": True,
                "handshake": {
                    "server": decoy_server,
                    "server_port": decoy_port,
                },
                "private_key": creds["private_key"],
                "short_id": creds["short_id"],
            },
        },
    }


def _build_tuic_server_inbound(creds, hosts, opts=None):
    pdef = PROTOCOL_DEFS["tuic"]
    return {
        "type": "tuic",
        "tag": pdef["inbound_tag"],
        "listen": "::",
        "listen_port": pdef["server_port"],
        "users": [{"uuid": creds["uuid"], "password": creds["pwd_tuic"]}],
        "congestion_control": "bbr",
        "zero_rtt_handshake": False,
        "heartbeat": "10s",
        "tls": {
            "enabled": True,
            "server_name": hosts["tuic"],
            "alpn": ["h3"],
            "certificate_path": pdef["cert_path"],
            "key_path": pdef["key_path"],
        },
    }


def _build_hy2_server_inbound(creds, hosts, opts=None):
    pdef = PROTOCOL_DEFS["hy2"]
    return {
        "type": "hysteria2",
        "tag": pdef["inbound_tag"],
        "listen": "::",
        "listen_port": pdef["server_port"],
        "users": [{"password": creds["pwd_hy2"]}],
        "ignore_client_bandwidth": False,
        "up_mbps": get_hy2_up_mbps(opts, server=True),
        "down_mbps": get_hy2_down_mbps(opts, server=True),
        "obfs": {"type": "salamander", "password": creds["pwd_obfs"]},
        "masquerade": get_hy2_masquerade_url(opts),
        "tls": {
            "enabled": True,
            "server_name": hosts["hy2"],
            "alpn": ["h3"],
            "certificate_path": pdef["cert_path"],
            "key_path": pdef["key_path"],
        },
    }


_SERVER_INBOUND_BUILDERS = {
    "anytls": _build_anytls_server_inbound,
    "tuic": _build_tuic_server_inbound,
    "hy2": _build_hy2_server_inbound,
}

# ---------------------------------------------------------------------------
# Client outbound builders (one per protocol)
# ---------------------------------------------------------------------------

def _build_anytls_client_outbound(creds, hosts, opts=None):
    decoy_server = get_reality_decoy_server(opts)
    return {
        "type": "anytls",
        "tag": PROTOCOL_DEFS["anytls"]["outbound_tag"],
        "server": hosts["reality"],
        "domain_resolver": build_domain_resolver(),
        "server_port": PROTOCOL_DEFS["anytls"]["server_port"],
        "tls": {
            "enabled": True,
            "server_name": decoy_server,
            "utls": {"enabled": True, "fingerprint": "chrome"},
            "reality": {
                "enabled": True,
                "public_key": creds["public_key"],
                "short_id": creds["short_id"],
            },
        },
        "password": creds["pwd_anytls"],
    }


def _build_tuic_client_outbound(creds, hosts, opts=None):
    return {
        "type": "tuic",
        "tag": PROTOCOL_DEFS["tuic"]["outbound_tag"],
        "server": hosts["tuic"],
        "domain_resolver": build_domain_resolver(),
        "server_port": PROTOCOL_DEFS["tuic"]["server_port"],
        "uuid": creds["uuid"],
        "password": creds["pwd_tuic"],
        "congestion_control": "bbr",
        "udp_relay_mode": "quic",
        "zero_rtt_handshake": False,
        "heartbeat": "10s",
        "tls": {
            "enabled": True,
            "server_name": hosts["tuic"],
            "alpn": ["h3"],
        },
    }


def _build_hy2_client_outbound(creds, hosts, opts=None):
    return {
        "type": "hysteria2",
        "tag": PROTOCOL_DEFS["hy2"]["outbound_tag"],
        "server": hosts["hy2"],
        "domain_resolver": build_domain_resolver(),
        "server_port": PROTOCOL_DEFS["hy2"]["server_port"],
        "up_mbps": get_hy2_up_mbps(opts),
        "down_mbps": get_hy2_down_mbps(opts),
        "obfs": {"type": "salamander", "password": creds["pwd_obfs"]},
        "password": creds["pwd_hy2"],
        "tls": {
            "enabled": True,
            "server_name": hosts["hy2"],
            "alpn": ["h3"],
        },
    }


_CLIENT_OUTBOUND_BUILDERS = {
    "anytls": _build_anytls_client_outbound,
    "tuic": _build_tuic_client_outbound,
    "hy2": _build_hy2_client_outbound,
}


# ---------------------------------------------------------------------------
# Composite builders
# ---------------------------------------------------------------------------

def _validate_protocols(enabled_protocols):
    unknown = [p for p in enabled_protocols if p not in PROTOCOL_DEFS]
    if unknown:
        raise ValueError(f"unknown protocol(s): {unknown}")
    if not enabled_protocols:
        raise ValueError("at least one protocol must be enabled")


def build_client_outbounds(creds, hosts, enabled_protocols=None, fingerprint_opts=None):
    if enabled_protocols is None:
        enabled_protocols = ALL_PROTOCOLS
    _validate_protocols(enabled_protocols)

    outbound_tags = [PROTOCOL_DEFS[p]["outbound_tag"] for p in enabled_protocols]

    result = [
        {
            "type": "selector",
            "tag": CLIENT_ROUTE_MODE_TAG,
            "outbounds": [CLIENT_ROUTE_TAG, CLIENT_PROXY_BEST_TAG, "direct"],
            "default": CLIENT_ROUTE_TAG,
            "interrupt_exist_connections": True,
        },
        {
            "type": "selector",
            "tag": CLIENT_PROXY_BEST_TAG,
            "outbounds": [CLIENT_PROXY_AUTO_TAG, *outbound_tags, CLIENT_ROUTE_TAG],
            "default": CLIENT_PROXY_AUTO_TAG,
            "interrupt_exist_connections": True,
        },
        {
            "type": "urltest",
            "tag": CLIENT_PROXY_AUTO_TAG,
            "outbounds": outbound_tags,
            "url": URLTEST_URL,
            "interval": "5m",
            "tolerance": 150,
            "interrupt_exist_connections": True,
        },
    ]

    for proto in enabled_protocols:
        result.append(_CLIENT_OUTBOUND_BUILDERS[proto](creds, hosts, fingerprint_opts))

    result.append({"type": "direct", "tag": CLIENT_ROUTE_TAG})
    result.append({"type": "direct", "tag": "direct"})
    result.append({"type": "block", "tag": "block"})
    return result


def build_server_config(creds, protocol_hosts=None, warp_mode="proxy", enabled_protocols=None, fingerprint_opts=None):
    if not protocol_hosts:
        raise ValueError("protocol_hosts is required")
    if enabled_protocols is None:
        enabled_protocols = ALL_PROTOCOLS
    _validate_protocols(enabled_protocols)

    hosts = protocol_hosts
    inbounds = [_SERVER_INBOUND_BUILDERS[p](creds, hosts, fingerprint_opts) for p in enabled_protocols]
    inbound_tags = [PROTOCOL_DEFS[p]["inbound_tag"] for p in enabled_protocols]

    outbound_tag = "warp-out" if warp_mode in ("proxy", "tun") else "direct"
    rules = []
    if "anytls" in enabled_protocols:
        rules.append({
            "inbound": PROTOCOL_DEFS["anytls"]["inbound_tag"],
            "action": "resolve",
            "server": SERVER_DNS_TAG,
            "strategy": "prefer_ipv4",
        })
        rules.append({
            "inbound": PROTOCOL_DEFS["anytls"]["inbound_tag"],
            "action": "sniff",
            "timeout": "1s",
        })
    rules.append({
        "inbound": inbound_tags,
        "action": "route",
        "outbound": outbound_tag,
    })

    return {
        "log": {"disabled": True},
        "dns": {
            "servers": [
                {
                    "type": "https",
                    "tag": SERVER_DNS_TAG,
                    "server": SERVER_DNS_SERVERS[0],
                    "path": "/dns-query",
                    "tls": {
                        "enabled": True,
                        "server_name": "cloudflare-dns.com",
                        "alpn": ["h2", "http/1.1"],
                    },
                },
            ],
        },
        "inbounds": inbounds,
        "outbounds": build_server_outbounds(warp_mode),
        "route": {
            "rules": rules,
            "final": outbound_tag,
            "default_domain_resolver": SERVER_DNS_TAG,
        },
    }


def build_client_config(creds, protocol_hosts=None, enabled_protocols=None, server_ip=None, fingerprint_opts=None):
    if not protocol_hosts:
        raise ValueError("protocol_hosts is required")
    if enabled_protocols is None:
        enabled_protocols = ALL_PROTOCOLS
    _validate_protocols(enabled_protocols)

    hosts = protocol_hosts

    return {
        "log": {
            "level": "debug",
            "timestamp": True,
        },
        "http_clients": [
            {
                "tag": "direct-client",
                "detour": "direct"
            }
        ],
        "dns": build_dns_config(hosts, enabled_protocols=enabled_protocols),
        "inbounds": [
            {
                "type": "tun",
                "tag": CLIENT_TUN_INBOUND_TAG,
                # Android expects standard tun addresses as an array.
                "address": CLIENT_TUN_ADDRESSES,
                "auto_route": True,
                "strict_route": True,
                "route_exclude_address": _client_tun_route_exclude(server_ip),
                "stack": CLIENT_TUN_STACK,
            }
        ],
        "outbounds": build_client_outbounds(creds, hosts, enabled_protocols, fingerprint_opts),
        "route": build_route_config(sniff_inbound=CLIENT_TUN_INBOUND_TAG, enabled_protocols=enabled_protocols),
    }


def protocol_ports(enabled_protocols=None):
    """Return list of (port, transport) tuples for the given protocols."""
    if enabled_protocols is None:
        enabled_protocols = ALL_PROTOCOLS
    return [
        (PROTOCOL_DEFS[p]["server_port"], PROTOCOL_DEFS[p]["transport"])
        for p in enabled_protocols
    ]
