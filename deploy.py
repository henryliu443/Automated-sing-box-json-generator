import json
import os
import subprocess

from config import DOMAIN_ROOT, build_client_config, build_protocol_hosts, build_server_config
from credentials import generate_credentials
from installer import ensure_dependencies
from watchdog import deploy_watchdog


def main():
    print("\n" + "🚀" * 10)
    print("Sing-box & Watchdog 一键部署")
    print("🚀" * 10)

    domain_input = input(f"请输入主域名 (默认: {DOMAIN_ROOT}): ").strip()
    if "://" in domain_input:
        domain_input = domain_input.split("://", 1)[1]
    domain_root = domain_input.split("/", 1)[0].strip().strip(".") or DOMAIN_ROOT
    protocol_hosts = build_protocol_hosts(domain_root)

    try:
        ensure_dependencies()
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
    subprocess.run(["systemctl", "restart", "sing-box"], check=True)

    print("\n✅ 部署成功")
    print("协议子域名映射:")
    print(f"  reality -> {protocol_hosts['reality']}")
    print(f"  hy2     -> {protocol_hosts['hy2']}")
    print(f"  tuic    -> {protocol_hosts['tuic']}")
    print("\n" + "=" * 20 + " 请全选复制客户端 JSON " + "=" * 20)
    print(json.dumps(cl_cfg, indent=2, ensure_ascii=False))
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
