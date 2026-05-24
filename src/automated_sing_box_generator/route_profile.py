import functools
import json
from pathlib import Path

_RULES_PATH = Path(__file__).parent / "rules.json"
_REQUIRED_BUCKETS = (
    "direct_exact", "proxy_exact",
    "direct_suffix", "proxy_suffix",
    "direct_keyword", "proxy_keyword",
    "direct_cidr", "proxy_cidr",
)

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

ROUTE_FINAL = "route-mode"
# Direct rule targets follow route-mode so switching to `global` can truly
# proxy domains listed in direct_* buckets (e.g. baidu.com).
DIRECT_RULE_OUTBOUND = ROUTE_FINAL
USE_GEOIP_CN = True


@functools.lru_cache(maxsize=1)
def _load_rules():
    """Lazy-load and validate rules.json on first access."""
    rules = json.loads(_RULES_PATH.read_text())
    for key in _REQUIRED_BUCKETS:
        if key not in rules:
            raise KeyError(f"rules.json missing required key: {key}")
        if not isinstance(rules[key], list):
            raise TypeError(f"rules.json[{key!r}] must be a list, got {type(rules[key]).__name__}")
    return rules


def _get_rules():
    """Return the loaded rules dict."""
    return _load_rules()


def _merge_unique(*groups):
    merged = []
    for group in groups:
        for item in group:
            if item not in merged:
                merged.append(item)
    return merged


def _protocol_host_domains(hosts, enabled_protocols=None):
    """Build the list of protocol host domains for DNS rules.

    Only includes hosts for protocols that are actually enabled.
    """
    if enabled_protocols is None:
        return [h for h in hosts.values()]
    from .config import PROTOCOL_DEFS
    domains = []
    for proto in enabled_protocols:
        host_key = PROTOCOL_DEFS[proto]["host_key"]
        if host_key in hosts:
            domains.append(hosts[host_key])
    return domains


def build_dns_config(hosts, enabled_protocols=None):
    """
    1.12.0+ 迁移重点：
    - 为拨号 DNS (如 DoH) 显式指定 domain_resolver
    """
    if not hosts:
        raise ValueError("hosts is required")

    rules = _load_rules()

    proto_domains = _protocol_host_domains(hosts, enabled_protocols)
    dns_rules = []
    if proto_domains:
        dns_rules.append({
            "domain": proto_domains,
            "server": "dns-direct",
        })

    direct_exact = _merge_unique(SKIP_PROXY_DOMAINS, DNS_DIRECT_ONLY_DOMAINS, rules["direct_exact"])
    direct_suffix = _merge_unique(SKIP_PROXY_SUFFIXES, DNS_DIRECT_ONLY_SUFFIXES, rules["direct_suffix"])
    proxy_suffix = _merge_unique(APNS_PROXY_SUFFIXES, rules["proxy_suffix"])

    dns_rules.append({"domain_suffix": APNS_PROXY_SUFFIXES, "server": "dns-remote"})
    if direct_exact:
        dns_rules.append({"domain": direct_exact, "server": "dns-direct"})
    if rules["proxy_exact"]:
        dns_rules.append({"domain": rules["proxy_exact"], "server": "dns-remote"})
    if direct_suffix:
        dns_rules.append({"domain_suffix": direct_suffix, "server": "dns-direct"})
    if proxy_suffix:
        dns_rules.append({"domain_suffix": proxy_suffix, "server": "dns-remote"})
    if rules["direct_keyword"]:
        dns_rules.append({"domain_keyword": rules["direct_keyword"], "server": "dns-direct"})
    if rules["proxy_keyword"]:
        dns_rules.append({"domain_keyword": rules["proxy_keyword"], "server": "dns-remote"})

    if USE_GEOIP_CN:
        dns_rules.append({"rule_set": "geosite-geolocation-!cn", "server": "dns-remote"})
        dns_rules.append({"rule_set": "geosite-cn", "server": "dns-direct"})

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
        "rules": dns_rules,
        "final": "dns-remote",
        "strategy": "prefer_ipv4",
    }


def build_route_config(sniff_inbound=None, enabled_protocols=None):
    """
    1.12.0+ 迁移重点：
    - 增加 default_domain_resolver
    """
    rules_data = _load_rules()

    rules = [
        {"protocol": "dns", "action": "hijack-dns"},
        {"ip_is_private": True, "action": "route", "outbound": "direct"},
        {"ip_cidr": DNS_DIRECT_SERVER, "action": "route", "outbound": "direct"},
    ]

    if sniff_inbound:
        rules.insert(0, {"inbound": sniff_inbound, "action": "sniff", "timeout": "1s"})
        rules.insert(0, {"inbound": sniff_inbound, "action": "resolve", "strategy": "prefer_ipv4"})

    direct_exact = _merge_unique(SKIP_PROXY_DOMAINS, rules_data["direct_exact"])
    direct_suffix = _merge_unique(SKIP_PROXY_SUFFIXES, rules_data["direct_suffix"])
    proxy_suffix = _merge_unique(APNS_PROXY_SUFFIXES, rules_data["proxy_suffix"])

    rules.append({"domain_suffix": APNS_PROXY_SUFFIXES, "action": "route", "outbound": "global"})
    if direct_exact:
        rules.append({"domain": direct_exact, "action": "route", "outbound": DIRECT_RULE_OUTBOUND})
    if rules_data["proxy_exact"]:
        rules.append({"domain": rules_data["proxy_exact"], "action": "route", "outbound": "global"})
    if direct_suffix:
        rules.append({"domain_suffix": direct_suffix, "action": "route", "outbound": DIRECT_RULE_OUTBOUND})

    # APNs IP rule must come after direct_suffix so that known Apple direct domains (like music.apple.com)
    # going to 17.x.x.x:443 aren't hijacked by the APNs proxy rule.
    rules.append({"ip_cidr": APNS_PROXY_CIDR, "port": APNS_PROXY_PORTS, "action": "route", "outbound": "global"})

    if proxy_suffix:
        rules.append({"domain_suffix": proxy_suffix, "action": "route", "outbound": "global"})
    if rules_data["direct_keyword"]:
        rules.append({"domain_keyword": rules_data["direct_keyword"], "action": "route", "outbound": DIRECT_RULE_OUTBOUND})
    if rules_data["proxy_keyword"]:
        rules.append({"domain_keyword": rules_data["proxy_keyword"], "action": "route", "outbound": "global"})
    if rules_data["direct_cidr"]:
        rules.append({"ip_cidr": rules_data["direct_cidr"], "action": "route", "outbound": DIRECT_RULE_OUTBOUND})
    if rules_data["proxy_cidr"]:
        rules.append({"ip_cidr": rules_data["proxy_cidr"], "action": "route", "outbound": "global"})

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
            },
            {
                "type": "remote",
                "tag": "geosite-cn",
                "format": "binary",
                "url": GEOSITE_CN_RULESET_URL,
            },
            {
                "type": "remote",
                "tag": "geoip-cn",
                "format": "binary",
                "url": GEOIP_CN_RULESET_URL,
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
    rules = _load_rules()
    parts = [
        f"direct: {len(rules['direct_exact'])}exact {len(rules['direct_suffix'])}suffix {len(rules['direct_keyword'])}kw {len(rules['direct_cidr'])}cidr",
        f"proxy: {len(rules['proxy_exact'])}exact {len(rules['proxy_suffix'])}suffix {len(rules['proxy_keyword'])}kw {len(rules['proxy_cidr'])}cidr",
    ]
    if USE_GEOIP_CN:
        parts.append("geosite-cn + geoip-cn")
    return " | ".join(parts)
