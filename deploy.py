import json
import os
import re
import subprocess
from typing import Any

from certs import ensure_tls_certificates
import cli_ui as ui
from config import (
    REALITY_DECOY_SERVER,
    build_client_config,
    build_protocol_hosts,
    build_server_config,
)
from credentials import generate_credentials
from installer import (
    deploy_singbox_auto_update,
    ensure_dependencies,
    ensure_port_safety,
    print_port_snapshot,
)
from watchdog import deploy_watchdog

DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
)
CF_TOKEN_ENV = "CF_Token"
CF_ZONE_ID_ENV = "CF_Zone_ID"
SING_BOX_CONFIG_PATH = "/etc/sing-box/config.json"
WATCHDOG_SCRIPT_PATH = "/root/warp_lazy_watchdog.sh"


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


def run_tls_issuance(protocol_hosts, cf_token, cf_zone_id):
    # Always set env for backward compatibility with older certs.py versions.
    os.environ[CF_TOKEN_ENV] = cf_token
    os.environ[CF_ZONE_ID_ENV] = cf_zone_id
    try:
        ensure_tls_certificates(protocol_hosts, cf_token=cf_token, cf_zone_id=cf_zone_id)
    except TypeError:
        ensure_tls_certificates(protocol_hosts)


def prompt_domain_root():
    ui.section("基础输入")
    return normalize_domain_input(ui.prompt("请输入主域名"))


def write_server_config(server_config: dict[str, Any]):
    os.makedirs(os.path.dirname(SING_BOX_CONFIG_PATH), exist_ok=True)
    with open(SING_BOX_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(server_config, f, indent=2, ensure_ascii=False)


def restart_services_and_verify(warp_mode):
    ui.section("服务重载")
    ui.step("先校验 sing-box 配置，再重启服务并执行端口校验")
    try:
        subprocess.run(["sing-box", "check", "-C", "/etc/sing-box"], check=True)
        subprocess.run(["systemctl", "restart", "sing-box"], check=True)
        ensure_port_safety(warp_mode)
    except (subprocess.CalledProcessError, RuntimeError) as e:
        raise RuntimeError(f"重启或端口校验失败: {e}") from e


def print_success_result(client_config, protocol_hosts, warp_mode):
    ui.section("部署结果")
    ui.success("部署成功")
    ui.kv("warp mode", warp_mode)
    ui.kv("reality", protocol_hosts["reality"])
    ui.kv("hy2", protocol_hosts["hy2"])
    ui.kv("tuic", protocol_hosts["tuic"])
    ui.kv("reality decoy", REALITY_DECOY_SERVER)
    print_port_snapshot()
    ui.json_block("客户端 JSON", client_config)


def deploy():
    domain_root = prompt_domain_root()
    protocol_hosts = build_protocol_hosts(domain_root)
    cf_token, cf_zone_id = resolve_cf_dns_credentials()

    ui.section("依赖检查")
    warp_mode = ensure_dependencies()

    ui.section("证书签发")
    run_tls_issuance(protocol_hosts, cf_token, cf_zone_id)

    ui.section("配置生成")
    ui.step("生成服务端和客户端配置")
    creds = generate_credentials()
    server_config = build_server_config(creds, protocol_hosts, warp_mode=warp_mode)
    client_config = build_client_config(creds, protocol_hosts)

    ui.step(f"写入服务端配置: {SING_BOX_CONFIG_PATH}")
    write_server_config(server_config)

    ui.section("守护任务")
    ui.step(f"部署 watchdog: {WATCHDOG_SCRIPT_PATH}")
    deploy_watchdog(WATCHDOG_SCRIPT_PATH, warp_mode=warp_mode)
    ui.step("部署 sing-box 自动更新任务")
    deploy_singbox_auto_update()
    restart_services_and_verify(warp_mode)
    print_success_result(client_config, protocol_hosts, warp_mode)


def main():
    ui.banner("Sing-box & Watchdog 一键部署", "统一初始化、证书签发、配置生成与守护部署")

    try:
        deploy()
    except RuntimeError as e:
        ui.error(str(e))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
