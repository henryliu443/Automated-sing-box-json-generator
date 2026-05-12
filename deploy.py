import json
import os
import re
import subprocess
from typing import Any, Optional

from certs import ensure_tls_certificates, needs_tls_certificates
from cloudflare_dns import detect_public_ipv4, sync_dns_records
import cli_ui as ui
from config import (
    ALL_PROTOCOLS,
    HY2_MASQUERADE_ENV,
    PROTOCOL_DEFS,
    REALITY_PORT_ENV,
    REALITY_SERVER_ENV,
    build_client_config,
    build_protocol_hosts,
    build_server_config,
    get_reality_decoy_server,
    protocol_ports,
)
from credentials import gen_subdomain_prefixes, generate_credentials
from installer import ensure_dependencies, ensure_port_safety, print_port_snapshot
from killswitch import deploy_killswitch_assets, killswitch_status
import state as state_mod
from watchdog import deploy_watchdog

DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
)
CF_TOKEN_ENV = "CF_Token"
CF_ZONE_ID_ENV = "CF_Zone_ID"
SING_BOX_CONFIG_PATH = "/etc/sing-box/config.json"
SING_BOX_WARP_CONFIG_PATH = "/etc/sing-box/config.warp.json"
SING_BOX_DIRECT_CONFIG_PATH = "/etc/sing-box/config.direct.json"
WATCHDOG_SCRIPT_PATH = "/root/warp_lazy_watchdog.sh"
SERVER_IP_ENV = "SERVER_IP"


def _merge_fingerprint_overrides(
    base: dict[str, str], overrides: Optional[dict[str, str]],
):
    """CLI / caller overrides win; *base* usually comes from prompts or prior state."""
    if not overrides:
        return dict(base)
    out = dict(base)
    for key in (REALITY_SERVER_ENV, REALITY_PORT_ENV, HY2_MASQUERADE_ENV):
        v = overrides.get(key)
        if v is not None and str(v).strip():
            out[key] = str(v).strip()
    return out


def normalize_domain_input(raw):
    value = raw.strip().lower()
    if "://" in value:
        value = value.split("://", 1)[1]
    value = value.split("/", 1)[0].split(":", 1)[0].strip().strip(".")
    if not value:
        raise RuntimeError("主域名不能为空")

    domain = value
    if not DOMAIN_RE.fullmatch(domain):
        raise RuntimeError(f"域名格式不合法: {domain}")
    return domain


def _sanitize_json_value(value: Any):
    if isinstance(value, str):
        return re.sub(r"[\ud800-\udfff]", "\uFFFD", value)
    if isinstance(value, dict):
        return {
            _sanitize_json_value(key): _sanitize_json_value(val)
            for key, val in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_json_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_json_value(item) for item in value)
    return value


def resolve_cf_dns_credentials():
    token = os.environ.get(CF_TOKEN_ENV, "").strip()
    zone_id = os.environ.get(CF_ZONE_ID_ENV, "").strip()

    if not token:
        token = ui.prompt("请输入 Cloudflare API Token", env_name=CF_TOKEN_ENV, secret=True).strip()
    else:
        ui.info(f"使用环境变量 {CF_TOKEN_ENV}")
    if not zone_id:
        zone_id = ui.prompt("请输入 Cloudflare Zone ID", env_name=CF_ZONE_ID_ENV).strip()
    else:
        ui.info(f"使用环境变量 {CF_ZONE_ID_ENV}")

    if not token or not zone_id:
        raise RuntimeError("Cloudflare DNS-01 凭据不能为空")
    return token, zone_id


def run_tls_issuance(protocol_hosts, cf_token, cf_zone_id, enabled_protocols=None):
    os.environ[CF_TOKEN_ENV] = cf_token
    os.environ[CF_ZONE_ID_ENV] = cf_zone_id
    ensure_tls_certificates(
        protocol_hosts,
        cf_token=cf_token,
        cf_zone_id=cf_zone_id,
        enabled_protocols=enabled_protocols,
    )


def prompt_domain_root():
    ui.section("基础输入")
    return normalize_domain_input(ui.prompt("请输入主域名"))


def prompt_protocols():
    ui.section("协议选择")
    available = [(name, PROTOCOL_DEFS[name]["label"]) for name in ALL_PROTOCOLS]
    return ui.select_protocols(available)


def _normalize_optional_input(raw):
    value = (raw or "").strip()
    return value or None


def prompt_server_ip():
    ui.section("服务器地址")
    env_value = _normalize_optional_input(os.environ.get(SERVER_IP_ENV))
    if env_value:
        ui.info(f"使用环境变量 {SERVER_IP_ENV}: {env_value}")
        return env_value
    raw = ui.prompt("请输入 VPS 公网 IP (可留空自动检测)", env_name=SERVER_IP_ENV)
    return _normalize_optional_input(raw)


def prompt_warp_mode():
    ui.section("WARP 模式")
    raw = ui.prompt("请选择 WARP 模式 [proxy/tun] (默认 proxy)").strip().lower()
    if not raw:
        return "proxy"
    if raw in {"proxy", "tun"}:
        return raw
    ui.warning(f"无效模式 {raw}，将使用默认 proxy")
    return "proxy"


def _prompt_env_if_empty(label, env_name, default_value):
    existing = _normalize_optional_input(os.environ.get(env_name))
    if existing:
        ui.info(f"使用环境变量 {env_name}")
        return existing
    raw = ui.prompt(f"{label} (默认: {default_value})", env_name=env_name).strip()
    if raw:
        return raw
    return default_value


def prompt_protocol_specific_inputs(enabled_protocols):
    ui.section("协议参数")
    captured = {}
    if "anytls" in enabled_protocols:
        captured[REALITY_SERVER_ENV] = _prompt_env_if_empty(
            "Reality server",
            REALITY_SERVER_ENV,
            "www.cloudflare.com",
        )
        captured[REALITY_PORT_ENV] = _prompt_env_if_empty(
            "Reality port",
            REALITY_PORT_ENV,
            "443",
        )
    if "hy2" in enabled_protocols:
        captured[HY2_MASQUERADE_ENV] = _prompt_env_if_empty(
            "Hysteria2 masquerade URL",
            HY2_MASQUERADE_ENV,
            "https://www.cloudflare.com",
        )
    return captured


def write_server_config(server_config: dict[str, Any], path=SING_BOX_CONFIG_PATH):
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(_sanitize_json_value(server_config), f, indent=2, ensure_ascii=False)


def activate_server_config(target=SING_BOX_WARP_CONFIG_PATH, link_path=SING_BOX_CONFIG_PATH):
    try:
        subprocess.run(["ln", "-sfn", target, link_path], check=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"激活 sing-box 配置失败: {e}") from e


def restart_services_and_verify(warp_mode, proto_ports=None):
    ui.section("服务重载")
    ui.step("先校验 sing-box 配置，再重启服务并执行端口校验")
    try:
        subprocess.run(["sing-box", "check", "-C", "/etc/sing-box"], check=True)
        subprocess.run(["systemctl", "restart", "sing-box"], check=True)
        ensure_port_safety(warp_mode, proto_ports)
    except (subprocess.CalledProcessError, RuntimeError) as e:
        raise RuntimeError(f"重启或端口校验失败: {e}") from e


def print_success_result(client_config, protocol_hosts, warp_mode, enabled_protocols=None, fingerprint_opts=None):
    if enabled_protocols is None:
        enabled_protocols = ALL_PROTOCOLS

    ui.section("部署结果")
    ui.success("部署成功")
    ui.kv("warp mode", warp_mode)
    for proto in enabled_protocols:
        host_key = PROTOCOL_DEFS[proto]["host_key"]
        ui.kv(proto, protocol_hosts[host_key])
    ui.kv("reality decoy", get_reality_decoy_server(fingerprint_opts))
    print_port_snapshot()
    ui.json_block("客户端 JSON", client_config)


def _desired_fqdns(phosts, enabled_protocols):
    """Return the set of FQDNs that need DNS A records right now."""
    fqdns = set()
    for proto in enabled_protocols:
        host_key = PROTOCOL_DEFS[proto]["host_key"]
        if host_key in phosts:
            fqdns.add(phosts[host_key])
    return fqdns


def deploy(domain_root=None, enabled_protocols=None, fingerprint_overrides=None):
    if domain_root is None:
        domain_root = prompt_domain_root()
    if enabled_protocols is None:
        enabled_protocols = prompt_protocols()
    protocol_inputs = _merge_fingerprint_overrides(
        prompt_protocol_specific_inputs(enabled_protocols),
        fingerprint_overrides,
    )
    preferred_warp_mode = prompt_warp_mode()

    # CF credentials are always required (DNS record management + optional TLS)
    cf_token, cf_zone_id = resolve_cf_dns_credentials()

    # Always generate fresh random prefixes — never reuse old ones.
    # sync_dns_records will clean up stale A records from previous deploys.
    old_state = state_mod.load_state()
    prefixes = gen_subdomain_prefixes()
    ui.info("已生成全新的随机子域名前缀")

    phosts = build_protocol_hosts(domain_root, prefixes)
    pports = protocol_ports(enabled_protocols)

    # Detect server public IP and sync Cloudflare DNS records
    ui.section("DNS 记录同步")
    server_ip = prompt_server_ip() or detect_public_ipv4()
    ui.kv("服务器公网 IP", server_ip)
    old_record_ids = old_state.get("dns_record_ids") if old_state else None
    dns_record_ids = sync_dns_records(
        cf_zone_id, cf_token,
        _desired_fqdns(phosts, enabled_protocols),
        server_ip, old_record_ids,
    )

    ui.section("依赖检查")
    warp_mode = ensure_dependencies(pports, preferred_warp_mode=preferred_warp_mode)

    need_certs = needs_tls_certificates(enabled_protocols)
    if need_certs:
        ui.section("证书签发")
        run_tls_issuance(phosts, cf_token, cf_zone_id, enabled_protocols)
    else:
        ui.info("所有启用的协议均不需要 TLS 证书，跳过签发")

    ui.section("配置生成")
    ui.step("生成服务端和客户端配置")
    creds = generate_credentials()
    server_config_warp = build_server_config(
        creds, phosts, warp_mode=warp_mode, enabled_protocols=enabled_protocols,
        fingerprint_opts=protocol_inputs,
    )
    server_config_direct = build_server_config(
        creds, phosts, warp_mode="none", enabled_protocols=enabled_protocols,
        fingerprint_opts=protocol_inputs,
    )
    client_config = build_client_config(
        creds,
        protocol_hosts=phosts,
        enabled_protocols=enabled_protocols,
        server_ip=server_ip,
        fingerprint_opts=protocol_inputs,
    )
    ui.section("抗识别优化")
    ui.success("Reality fingerprint alignment")
    ui.success("QUIC behavior normalization")
    if "hy2" in enabled_protocols:
        ui.success("Bandwidth shaping (hy2)")
    ui.success("Protocol-aware parameter injection")

    ui.step(f"写入服务端配置: {SING_BOX_CONFIG_PATH}")
    write_server_config(server_config_warp, SING_BOX_WARP_CONFIG_PATH)
    write_server_config(server_config_direct, SING_BOX_DIRECT_CONFIG_PATH)
    activate_server_config()

    ui.section("保存部署状态")
    state_mod.save_state({
        "domain_root": domain_root,
        "subdomain_prefixes": prefixes,
        "protocol_hosts": phosts,
        "enabled_protocols": enabled_protocols,
        "credentials": creds,
        "warp_mode": warp_mode,
        "server_ip": server_ip,
        "dns_record_ids": dns_record_ids,
        "anti_detection": protocol_inputs,
        "preferred_warp_mode": preferred_warp_mode,
    })
    ui.success("部署状态已保存")

    ui.section("守护任务")
    ui.step(f"部署 watchdog: {WATCHDOG_SCRIPT_PATH}")
    deploy_watchdog(WATCHDOG_SCRIPT_PATH, warp_mode=warp_mode)
    ui.step("部署 VPS VPN kill switch 控制脚本")
    deploy_killswitch_assets()
    restart_services_and_verify(warp_mode, pports)
    print_success_result(client_config, phosts, warp_mode, enabled_protocols, fingerprint_opts=protocol_inputs)


def reconfigure(enabled_protocols=None):
    """Regenerate and apply configs using saved deployment state."""
    loaded = state_mod.load_state()
    if not loaded:
        raise RuntimeError("未找到部署状态，请先运行 deploy")

    if enabled_protocols is None:
        enabled_protocols = loaded.get("enabled_protocols", ALL_PROTOCOLS)

    creds = loaded["credentials"]
    phosts = loaded["protocol_hosts"]
    warp_mode = loaded["warp_mode"]
    pports = protocol_ports(enabled_protocols)

    # If protocol selection changed, sync DNS records accordingly
    old_protocols = set(loaded.get("enabled_protocols", ALL_PROTOCOLS))
    if set(enabled_protocols) != old_protocols:
        ui.section("DNS 记录同步 (协议变更)")
        cf_token, cf_zone_id = resolve_cf_dns_credentials()
        server_ip = loaded.get("server_ip") or detect_public_ipv4()
        old_record_ids = loaded.get("dns_record_ids")
        dns_record_ids = sync_dns_records(
            cf_zone_id, cf_token,
            _desired_fqdns(phosts, enabled_protocols),
            server_ip, old_record_ids,
        )
        loaded["dns_record_ids"] = dns_record_ids
        loaded["server_ip"] = server_ip

    ui.section("配置生成")
    ui.step("生成服务端和客户端配置")
    opts = loaded.get("anti_detection")
    server_config_warp = build_server_config(
        creds, phosts, warp_mode=warp_mode, enabled_protocols=enabled_protocols,
        fingerprint_opts=opts,
    )
    server_config_direct = build_server_config(
        creds, phosts, warp_mode="none", enabled_protocols=enabled_protocols,
        fingerprint_opts=opts,
    )
    client_config = build_client_config(
        creds,
        protocol_hosts=phosts,
        enabled_protocols=enabled_protocols,
        server_ip=loaded.get("server_ip"),
        fingerprint_opts=opts,
    )

    ui.step(f"写入服务端配置: {SING_BOX_CONFIG_PATH}")
    write_server_config(server_config_warp, SING_BOX_WARP_CONFIG_PATH)
    write_server_config(server_config_direct, SING_BOX_DIRECT_CONFIG_PATH)
    activate_server_config()

    loaded["enabled_protocols"] = enabled_protocols
    state_mod.save_state(loaded)

    restart_services_and_verify(warp_mode, pports)
    print_success_result(client_config, phosts, warp_mode, enabled_protocols, fingerprint_opts=opts)


def show_status():
    loaded = state_mod.load_state()
    if loaded:
        ui.section("部署状态")
        ui.kv("域名", loaded.get("domain_root", "?"))
        ui.kv("协议", ", ".join(loaded.get("enabled_protocols", [])))
        ui.kv("WARP 模式", loaded.get("warp_mode", "?"))
        ui.kv("服务器 IP", loaded.get("server_ip", "?"))
        ui.kv("部署时间", loaded.get("deployed_at", "?"))

        dns_ids = loaded.get("dns_record_ids")
        if dns_ids:
            ui.section("DNS 记录 (Cloudflare 托管)")
            for fqdn, rid in dns_ids.items():
                ui.kv(fqdn, f"record_id={rid[:12]}...")
    else:
        ui.warning("未找到部署状态")

    from installer import get_singbox_version, warp_proxy_ready, warp_tunnel_ready

    ui.section("服务状态")
    version = get_singbox_version()
    if version:
        ui.success(f"sing-box: {version}")
    else:
        ui.error("sing-box 未安装或不可用")

    if warp_proxy_ready():
        ui.success("WARP: 本地代理模式正常")
    elif warp_tunnel_ready():
        ui.success("WARP: 系统隧道模式正常")
    else:
        ui.warning("WARP 未就绪")

    ui.kv("VPN kill switch", killswitch_status())

    try:
        print_port_snapshot()
    except RuntimeError:
        pass


def main(enabled_protocols=None, domain_root=None, fingerprint_overrides=None):
    ui.banner("Sing-box & Watchdog 一键部署", "统一初始化、证书签发、配置生成与守护部署")

    try:
        deploy(
            domain_root=domain_root,
            enabled_protocols=enabled_protocols,
            fingerprint_overrides=fingerprint_overrides,
        )
    except RuntimeError as e:
        ui.error(str(e))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
