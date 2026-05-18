import json
from pathlib import Path

_RULES_PATH = Path(__file__).parent / "rules.json"
_REQUIRED_BUCKETS = (
    "direct_exact", "proxy_exact",
    "direct_suffix", "proxy_suffix",
    "direct_keyword", "proxy_keyword",
    "direct_cidr", "proxy_cidr",
)

_rules = json.loads(_RULES_PATH.read_text())
for _key in _REQUIRED_BUCKETS:
    if _key not in _rules:
        raise KeyError(f"rules.json missing required key: {_key}")
    if not isinstance(_rules[_key], list):
        raise TypeError(f"rules.json[{_key!r}] must be a list, got {type(_rules[_key]).__name__}")

DNS_DIRECT_SERVER = ["223.5.5.5", "119.29.29.29"]
DNS_REMOTE_SERVER = "1.1.1.1"
DNS_REMOTE_PATH = "/dns-query"
DNS_REMOTE_TLS_SERVER_NAME = "cloudflare-dns.com"
GEOIP_CN_RULESET_URL = "https://testingcf.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@sing/geo/geoip/cn.srs"
GEOSITE_CN_RULESET_URL = "https://testingcf.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@sing/geo/geosite/cn.srs"
GEOSITE_GEOLOCATION_NON_CN_RULESET_URL = "https://testingcf.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@sing/geo/geosite/geolocation-!cn.srs"

SKIP_PROXY_DOMAINS = ["localhost", "captive.apple.com"]
SKIP_PROXY_SUFFIXES = ["local"]
DNS_DIRECT_ONLY_DOMAINS = ["cp.cloudflare.com"]
DNS_DIRECT_ONLY_SUFFIXES = ["in-addr.arpa", "ip6.arpa"]
APNS_PROXY_SUFFIXES = ["push.apple.com"]
APNS_PROXY_CIDR = [
    "17.0.0.0/8",
    "2403:300:a42::/48",
    "2403:300:a51::/48",
    "2620:149:a44::/48",
    "2a01:b740:a42::/48",
]
APNS_PROXY_PORTS = [443, 5223, 2197]
TUN_EXCLUDED_ROUTES = [
    # Android VpnService automatically excludes loopback (127.0.0.0/8) and
    # link-local (169.254.0.0/16). Attempting to exclude them explicitly
    # triggers "configure tun interface: Bad address". See sing-box #2030.
    "10.0.0.0/8",
    "100.64.0.0/10",
    "172.16.0.0/12",
    "192.168.0.0/16",
]

DIRECT_EXACT   = _rules["direct_exact"]
PROXY_EXACT    = _rules["proxy_exact"]
DIRECT_SUFFIX  = _rules["direct_suffix"]
PROXY_SUFFIX   = _rules["proxy_suffix"]
DIRECT_KEYWORD = _rules["direct_keyword"]
PROXY_KEYWORD  = _rules["proxy_keyword"]
DIRECT_CIDR    = _rules["direct_cidr"]
PROXY_CIDR     = _rules["proxy_cidr"]

IGNORED_RULES = [
    "IP-ASN,132203,DIRECT,no-resolve", "USER-AGENT,Line*,PROXY",
]

ROUTE_FINAL = "route-mode"
# Direct rule targets follow route-mode so switching to `global` can truly
# proxy domains listed in direct_* buckets (e.g. baidu.com).
DIRECT_RULE_OUTBOUND = ROUTE_FINAL
USE_GEOIP_CN = True


def _merge_unique(*groups):
    merged = []
    for group in groups:
        for item in group:
            if item not in merged:
                merged.append(item)
    return merged


def build_dns_config(hosts, compact=False):
    """
    1.12.0+ 迁移重点：
    - 为拨号 DNS (如 DoH) 显式指定 domain_resolver
    """
    if not hosts:
        raise ValueError("hosts is required")

    rules = [
        {
            "domain": [hosts["reality"], hosts["tuic"], hosts["hy2"]],
            "server": "dns-direct",
        }
    ]

    if compact:
        # Compact mode: only basic rules and rule_sets
        if USE_GEOIP_CN:
            rules.append({"rule_set": "geosite-cn", "server": "dns-direct"})
    else:
        direct_exact = _merge_unique(SKIP_PROXY_DOMAINS, DNS_DIRECT_ONLY_DOMAINS, DIRECT_EXACT)
        direct_suffix = _merge_unique(SKIP_PROXY_SUFFIXES, DNS_DIRECT_ONLY_SUFFIXES, DIRECT_SUFFIX)
        proxy_suffix = _merge_unique(APNS_PROXY_SUFFIXES, PROXY_SUFFIX)

        rules.append({"domain_suffix": APNS_PROXY_SUFFIXES, "server": "dns-remote"})
        if direct_exact:
            rules.append({"domain": direct_exact, "server": "dns-direct"})
        if PROXY_EXACT:
            rules.append({"domain": PROXY_EXACT, "server": "dns-remote"})
        if direct_suffix:
            rules.append({"domain_suffix": direct_suffix, "server": "dns-direct"})
        if proxy_suffix:
            rules.append({"domain_suffix": proxy_suffix, "server": "dns-remote"})
        if DIRECT_KEYWORD:
            rules.append({"domain_keyword": DIRECT_KEYWORD, "server": "dns-direct"})
        if PROXY_KEYWORD:
            rules.append({"domain_keyword": PROXY_KEYWORD, "server": "dns-remote"})

        if USE_GEOIP_CN:
            rules.append({"rule_set": "geosite-geolocation-!cn", "server": "dns-remote"})
            rules.append({"rule_set": "geosite-cn", "server": "dns-direct"})

    direct_dns_servers = [
        {
            "type": "udp",
            "tag": "dns-direct" if i == 0 else f"dns-direct-{i}",
            "server": server_ip,
        } for i, server_ip in enumerate(DNS_DIRECT_SERVER)
    ]

    return {
        "servers": [
            *direct_dns_servers,
            {
                "type": "https",
                "tag": "dns-remote",
                "server": DNS_REMOTE_SERVER,
                "path": DNS_REMOTE_PATH,
                "tls": {
                    "enabled": True,
                    "server_name": DNS_REMOTE_TLS_SERVER_NAME,
                    "alpn": ["h2", "http/1.1"],
                },
                "detour": "global",
                "domain_resolver": "dns-direct",
            },
        ],
        "rules": rules,
        "final": "dns-remote",
        "strategy": "prefer_ipv4",
    }


def build_route_config(sniff_inbound=None, compact=False):
    """
    1.12.0+ 迁移重点：
    - 增加 default_domain_resolver
    """
    rules = [
        {"protocol": "dns", "action": "hijack-dns"},
        {"ip_is_private": True, "action": "route", "outbound": "direct"},
        {"ip_cidr": DNS_DIRECT_SERVER, "action": "route", "outbound": "direct"},
    ]

    if sniff_inbound:
        rules.insert(0, {"inbound": sniff_inbound, "action": "sniff", "timeout": "1s"})
        rules.insert(0, {"inbound": sniff_inbound, "action": "resolve", "strategy": "prefer_ipv4"})

    if compact:
        # Compact mode: omit large embedded rule lists
        pass
    else:
        direct_exact = _merge_unique(SKIP_PROXY_DOMAINS, DIRECT_EXACT)
        direct_suffix = _merge_unique(SKIP_PROXY_SUFFIXES, DIRECT_SUFFIX)
        proxy_suffix = _merge_unique(APNS_PROXY_SUFFIXES, PROXY_SUFFIX)

        rules.append({"domain_suffix": APNS_PROXY_SUFFIXES, "action": "route", "outbound": "global"})
        if direct_exact:
            rules.append({"domain": direct_exact, "action": "route", "outbound": DIRECT_RULE_OUTBOUND})
        if PROXY_EXACT:
            rules.append({"domain": PROXY_EXACT, "action": "route", "outbound": "global"})
        if direct_suffix:
            rules.append({"domain_suffix": direct_suffix, "action": "route", "outbound": DIRECT_RULE_OUTBOUND})
        
        # APNs IP rule must come after direct_suffix so that known Apple direct domains (like music.apple.com)
        # going to 17.x.x.x:443 aren't hijacked by the APNs proxy rule.
        rules.append({"ip_cidr": APNS_PROXY_CIDR, "port": APNS_PROXY_PORTS, "action": "route", "outbound": "global"})
        
        if proxy_suffix:
            rules.append({"domain_suffix": proxy_suffix, "action": "route", "outbound": "global"})
        if DIRECT_KEYWORD:
            rules.append({"domain_keyword": DIRECT_KEYWORD, "action": "route", "outbound": DIRECT_RULE_OUTBOUND})
        if PROXY_KEYWORD:
            rules.append({"domain_keyword": PROXY_KEYWORD, "action": "route", "outbound": "global"})
        if DIRECT_CIDR:
            rules.append({"ip_cidr": DIRECT_CIDR, "action": "route", "outbound": DIRECT_RULE_OUTBOUND})
        if PROXY_CIDR:
            rules.append({"ip_cidr": PROXY_CIDR, "action": "route", "outbound": "global"})

    route = {
        "rules": rules,
        "final": ROUTE_FINAL,
        "auto_detect_interface": True,
        "default_domain_resolver": "dns-direct",
    }

    if USE_GEOIP_CN:
        route["rule_set"] = [
            {
                "type": "remote",
                "tag": "geosite-geolocation-!cn",
                "format": "binary",
                "url": GEOSITE_GEOLOCATION_NON_CN_RULESET_URL,
                "download_detour": "direct",
            },
            {
                "type": "remote",
                "tag": "geosite-cn",
                "format": "binary",
                "url": GEOSITE_CN_RULESET_URL,
                "download_detour": "direct",
            },
            {
                "type": "remote",
                "tag": "geoip-cn",
                "format": "binary",
                "url": GEOIP_CN_RULESET_URL,
                "download_detour": "direct",
            },
        ]
        route["rules"].append(
            {"rule_set": "geosite-geolocation-!cn", "action": "route", "outbound": "global"}
        )
        route["rules"].append(
            {"rule_set": "geosite-cn", "action": "route", "outbound": DIRECT_RULE_OUTBOUND}
        )
        route["rules"].append(
            {"rule_set": "geoip-cn", "action": "route", "outbound": DIRECT_RULE_OUTBOUND}
        )

    return route


def rule_summary():
    """Return a compact string summarising loaded rule counts."""
    parts = [
        f"direct: {len(DIRECT_EXACT)}exact {len(DIRECT_SUFFIX)}suffix {len(DIRECT_KEYWORD)}kw {len(DIRECT_CIDR)}cidr",
        f"proxy: {len(PROXY_EXACT)}exact {len(PROXY_SUFFIX)}suffix {len(PROXY_KEYWORD)}kw {len(PROXY_CIDR)}cidr",
    ]
    if USE_GEOIP_CN:
        parts.append("geosite-cn + geoip-cn")
    return " | ".join(parts)
