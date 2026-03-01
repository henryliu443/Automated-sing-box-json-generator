import json
import os
import re
import subprocess

from certs import ensure_tls_certificates
from config import (
    DOMAIN_ROOT,
    REALITY_DECOY_SERVER,
    build_client_config,
    build_protocol_hosts,
    build_server_config,
)
from credentials import generate_credentials
from installer import ensure_dependencies, ensure_port_safety, print_port_snapshot
from watchdog import deploy_watchdog

DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
)
CF_TOKEN_ENV = "CF_Token"
CF_ZONE_ID_ENV = "CF_Zone_ID"


def normalize_domain_input(raw):
    value = raw.strip().lower()
    if "://" in value:
        value = value.split("://", 1)[1]
    value = value.split("/", 1)[0].split(":", 1)[0].strip().strip(".")
    domain = value or DOMAIN_ROOT
    if not DOMAIN_RE.fullmatch(domain):
        raise RuntimeError(f"域名格式不合法: {domain}")
    return domain


def resolve_cf_dns_credentials():
    token = os.environ.get(CF_TOKEN_ENV, "").strip()
    zone_id = os.environ.get(CF_ZONE_ID_ENV, "").strip()

    if not token:
        token = input(f"请输入 Cloudflare API Token ({CF_TOKEN_ENV}): ").strip()
    if not zone_id:
        zone_id = input(f"请输入 Cloudflare Zone ID ({CF_ZONE_ID_ENV}): ").strip()

    if not token or not zone_id:
        raise RuntimeError("Cloudflare DNS-01 凭据不能为空")
    return token, zone_id


def main():
    print("\n" + "🚀" * 10)
    print("Sing-box & Watchdog 一键部署")
    print("🚀" * 10)

    try:
        domain_root = normalize_domain_input(input(f"请输入主域名 (默认: {DOMAIN_ROOT}): "))
    except RuntimeError as e:
        print(str(e))
        return 1
    protocol_hosts = build_protocol_hosts(domain_root)

    try:
        cf_token, cf_zone_id = resolve_cf_dns_credentials()
    except RuntimeError as e:
        print(str(e))
        return 1

    try:
        ensure_dependencies()
    except RuntimeError as e:
        print(str(e))
        return 1

    try:
        ensure_tls_certificates(protocol_hosts, cf_token=cf_token, cf_zone_id=cf_zone_id)
    except RuntimeError as e:
        print(str(e))
        return 1

    creds = generate_credentials()
    sv_cfg = build_server_config(creds, protocol_hosts)
    cl_cfg = build_client_config(creds, protocol_hosts)

    os.makedirs("/etc/sing-box", exist_ok=True)
    with open("/etc/sing-box/config.json", "w", encoding="utf-8") as f:
        json.dump(sv_cfg, f, indent=2, ensure_ascii=False)

    deploy_watchdog("/root/warp_lazy_watchdog.sh")

    print("正在重启 sing-box...")
    try:
        subprocess.run(["systemctl", "restart", "sing-box"], check=True)
        ensure_port_safety()
    except (subprocess.CalledProcessError, RuntimeError) as e:
        print(f"重启或端口校验失败: {e}")
        return 1

    print("\n✅ 部署成功")
    print("协议子域名映射:")
    print(f"  reality -> {protocol_hosts['reality']}")
    print(f"  hy2     -> {protocol_hosts['hy2']}")
    print(f"  tuic    -> {protocol_hosts['tuic']}")
    print(f"Reality 伪装握手域名 -> {REALITY_DECOY_SERVER}")
    print_port_snapshot()
    print("\n" + "=" * 20 + " 请全选复制客户端 JSON " + "=" * 20)
    print(json.dumps(cl_cfg, indent=2, ensure_ascii=False))
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
