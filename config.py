from route_profile import TUN_EXCLUDED_ROUTES, build_dns_config, build_route_config


REALITY_DECOY_SERVER = "react.dev"
REALITY_DECOY_PORT = 443
HY2_MASQUERADE_URL = "https://www.cloudflare.com"

TUIC_CERT_PATH = "/etc/sing-box-tuic/certs/tuic.crt"
TUIC_KEY_PATH = "/etc/sing-box-tuic/certs/tuic.key"
HY2_CERT_PATH = "/etc/hysteria/server.crt"
HY2_KEY_PATH = "/etc/hysteria/server.key"

CLIENT_TUN_INBOUND_TAG = "tun-in"
CLIENT_PROXY_BEST_TAG = "proxy-best"
CLIENT_PROXY_AUTO_TAG = "proxy-auto"
CLIENT_ROUTE_MODE_TAG = "route-mode"
CLIENT_GLOBAL_TAG = "global"

SERVER_DNS_SERVERS = ("1.1.1.1", "1.0.0.1")
SERVER_DNS_TAG = "dns-server"

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


# ---------------------------------------------------------------------------
# Server inbound builders (one per protocol)
# ---------------------------------------------------------------------------

def _build_anytls_server_inbound(creds, hosts):
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
            "server_name": REALITY_DECOY_SERVER,
            "reality": {
                "enabled": True,
                "handshake": {
                    "server": REALITY_DECOY_SERVER,
                    "server_port": REALITY_DECOY_PORT,
                },
                "private_key": creds["private_key"],
                "short_id": creds["short_id"],
            },
        },
    }


def _build_tuic_server_inbound(creds, hosts):
    pdef = PROTOCOL_DEFS["tuic"]
    return {
        "type": "tuic",
        "tag": pdef["inbound_tag"],
        "listen": "::",
        "listen_port": pdef["server_port"],
        "users": [{"uuid": creds["uuid"], "password": creds["pwd_tuic"]}],
        "congestion_control": "bbr",
        "zero_rtt_handshake": True,
        "tls": {
            "enabled": True,
            "server_name": hosts["tuic"],
            "certificate_path": pdef["cert_path"],
            "key_path": pdef["key_path"],
        },
    }


def _build_hy2_server_inbound(creds, hosts):
    pdef = PROTOCOL_DEFS["hy2"]
    return {
        "type": "hysteria2",
        "tag": pdef["inbound_tag"],
        "listen": "::",
        "listen_port": pdef["server_port"],
        "users": [{"password": creds["pwd_hy2"]}],
        "ignore_client_bandwidth": True,
        "obfs": {"type": "salamander", "password": creds["pwd_obfs"]},
        "masquerade": HY2_MASQUERADE_URL,
        "tls": {
            "enabled": True,
            "server_name": hosts["hy2"],
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

def _build_anytls_client_outbound(creds, hosts):
    return {
        "type": "anytls",
        "tag": PROTOCOL_DEFS["anytls"]["outbound_tag"],
        "server": hosts["reality"],
        "domain_resolver": build_domain_resolver(),
        "server_port": PROTOCOL_DEFS["anytls"]["server_port"],
        "tls": {
            "enabled": True,
            "server_name": REALITY_DECOY_SERVER,
            "utls": {"enabled": True, "fingerprint": "chrome"},
            "reality": {
                "enabled": True,
                "public_key": creds["public_key"],
                "short_id": creds["short_id"],
            },
        },
        "password": creds["pwd_anytls"],
    }


def _build_tuic_client_outbound(creds, hosts):
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
        "tls": {
            "enabled": True,
            "server_name": hosts["tuic"],
        },
    }


def _build_hy2_client_outbound(creds, hosts):
    return {
        "type": "hysteria2",
        "tag": PROTOCOL_DEFS["hy2"]["outbound_tag"],
        "server": hosts["hy2"],
        "domain_resolver": build_domain_resolver(),
        "server_port": PROTOCOL_DEFS["hy2"]["server_port"],
        "obfs": {"type": "salamander", "password": creds["pwd_obfs"]},
        "password": creds["pwd_hy2"],
        "tls": {
            "enabled": True,
            "server_name": hosts["hy2"],
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

def build_client_outbounds(creds, hosts, enabled_protocols=None):
    if enabled_protocols is None:
        enabled_protocols = ALL_PROTOCOLS

    outbound_tags = [PROTOCOL_DEFS[p]["outbound_tag"] for p in enabled_protocols]

    result = [
        {
            "type": "selector",
            "tag": CLIENT_ROUTE_MODE_TAG,
            "outbounds": ["direct", CLIENT_GLOBAL_TAG],
            "default": "direct",
            "interrupt_exist_connections": True,
        },
        {
            "type": "selector",
            "tag": CLIENT_PROXY_BEST_TAG,
            "outbounds": [CLIENT_PROXY_AUTO_TAG, *outbound_tags, "direct"],
            "default": CLIENT_PROXY_AUTO_TAG,
            "interrupt_exist_connections": True,
        },
        {
            "type": "urltest",
            "tag": CLIENT_PROXY_AUTO_TAG,
            "outbounds": outbound_tags,
            "url": "https://cp.cloudflare.com/generate_204",
            "interval": "10m",
            "tolerance": 50,
        },
        {
            "type": "urltest",
            "tag": CLIENT_GLOBAL_TAG,
            "outbounds": outbound_tags,
            "url": "https://cp.cloudflare.com/generate_204",
            "interval": "10m",
            "tolerance": 50,
        },
    ]

    for proto in enabled_protocols:
        result.append(_CLIENT_OUTBOUND_BUILDERS[proto](creds, hosts))

    result.append({"type": "direct", "tag": "direct"})
    return result


def build_server_config(creds, protocol_hosts=None, warp_mode="proxy", enabled_protocols=None):
    if not protocol_hosts:
        raise ValueError("protocol_hosts is required")
    if enabled_protocols is None:
        enabled_protocols = ALL_PROTOCOLS

    hosts = protocol_hosts
    inbounds = [_SERVER_INBOUND_BUILDERS[p](creds, hosts) for p in enabled_protocols]
    inbound_tags = [PROTOCOL_DEFS[p]["inbound_tag"] for p in enabled_protocols]

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
        "outbound": "warp-out",
    })

    return {
        "log": {"disabled": True},
        "dns": {
            "servers": [
                {
                    "type": "udp",
                    "tag": SERVER_DNS_TAG,
                    "server": SERVER_DNS_SERVERS[0],
                },
            ],
        },
        "inbounds": inbounds,
        "outbounds": build_server_outbounds(warp_mode),
        "route": {
            "rules": rules,
            "final": "warp-out",
            "default_domain_resolver": SERVER_DNS_TAG,
        },
    }


def build_client_config(creds, protocol_hosts=None, enabled_protocols=None):
    if not protocol_hosts:
        raise ValueError("protocol_hosts is required")
    if enabled_protocols is None:
        enabled_protocols = ALL_PROTOCOLS

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
        "outbounds": build_client_outbounds(creds, hosts, enabled_protocols),
        "route": build_route_config(sniff_inbound=CLIENT_TUN_INBOUND_TAG),
    }


def protocol_ports(enabled_protocols=None):
    """Return list of (port, transport) tuples for the given protocols."""
    if enabled_protocols is None:
        enabled_protocols = ALL_PROTOCOLS
    return [
        (PROTOCOL_DEFS[p]["server_port"], PROTOCOL_DEFS[p]["transport"])
        for p in enabled_protocols
    ]
