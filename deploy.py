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
from frontend import deploy_fake_frontend
from installer import ensure_dependencies, ensure_port_safety, print_port_snapshot
from watchdog import deploy_watchdog

DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
)


def normalize_domain_input(raw):
    value = raw.strip().lower()
    if "://" in value:
        value = value.split("://", 1)[1]
    value = value.split("/", 1)[0].split(":", 1)[0].strip().strip(".")
    domain = value or DOMAIN_ROOT
    if not DOMAIN_RE.fullmatch(domain):
        raise RuntimeError(f"域名格式不合法: {domain}")
    return domain


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
        ensure_dependencies()
    except RuntimeError as e:
        print(str(e))
        return 1

    try:
        deploy_fake_frontend(domain_root, protocol_hosts)
        ensure_port_safety(require_nginx_listener=True)
    except RuntimeError as e:
        print(str(e))
        return 1

    try:
        ensure_tls_certificates(protocol_hosts)
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
        ensure_port_safety(require_nginx_listener=True)
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
