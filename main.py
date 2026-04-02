import argparse
import importlib
import os
import sys
import time
import urllib.request
from urllib.error import URLError

try:
    import cli_ui as ui
except ModuleNotFoundError:
    class _FallbackUI:
        @staticmethod
        def banner(title, subtitle=None):
            print(f"=== {title} ===")
            if subtitle:
                print(subtitle)

        @staticmethod
        def step(message):
            print(f"[STEP] {message}")

        @staticmethod
        def info(message):
            print(f"[INFO] {message}")

        @staticmethod
        def error(message):
            print(f"[ERR ] {message}")

        @staticmethod
        def success(message):
            print(f"[ OK ] {message}")

    ui = _FallbackUI()

BASE_URL = "https://raw.githubusercontent.com/henryliu443/Automated-sing-box-json-generator/refs/heads/main"
REQUIRED_FILES = [
    "deploy.py",
    "cli_ui.py",
    "config.py",
    "route_profile.py",
    "certs.py",
    "installer.py",
    "credentials.py",
    "watchdog.py",
    "state.py",
    "export.py",
    "cloudflare_dns.py",
    "rules.json",
]


def download_file(name):
    url = f"{BASE_URL}/{name}?ts={int(time.time())}"
    with urllib.request.urlopen(url, timeout=20) as resp:
        content = resp.read()
    with open(name, "wb") as f:
        f.write(content)


def refresh_required_files():
    for name in REQUIRED_FILES:
        ui.step(f"刷新远程文件: {name}")
        try:
            download_file(name)
        except (URLError, TimeoutError) as e:
            raise RuntimeError(f"bootstrap download failed: {name}: {e}") from e


def should_refresh_from_remote():
    return not os.path.isdir(".git")


# ---------------------------------------------------------------------------
# CLI sub-command handlers
# ---------------------------------------------------------------------------

def _parse_protocols(value):
    if not value:
        return None
    return [p.strip() for p in value.split(",") if p.strip()]


def cmd_deploy(args):
    deploy = importlib.import_module("deploy")
    protocols = _parse_protocols(args.protocols) if args.protocols else None
    domain = args.domain or None
    raise SystemExit(deploy.main(enabled_protocols=protocols, domain_root=domain))


def cmd_install(args):
    ui_mod = importlib.import_module("cli_ui")
    installer = importlib.import_module("installer")
    ui_mod.banner("依赖安装", "WARP、sing-box 安装检查")
    try:
        installer.ensure_dependencies()
        ui_mod.success("依赖安装完成")
    except RuntimeError as e:
        ui_mod.error(str(e))
        raise SystemExit(1)


def cmd_config(args):
    deploy = importlib.import_module("deploy")
    ui_mod = importlib.import_module("cli_ui")
    ui_mod.banner("重新生成配置", "使用已保存的部署状态重新生成并应用配置")
    protocols = _parse_protocols(args.protocols) if args.protocols else None
    try:
        deploy.reconfigure(enabled_protocols=protocols)
    except RuntimeError as e:
        ui_mod.error(str(e))
        raise SystemExit(1)


def cmd_export(args):
    export = importlib.import_module("export")
    ui_mod = importlib.import_module("cli_ui")
    try:
        export.export_client_config(fmt=args.format, output=args.output)
    except RuntimeError as e:
        ui_mod.error(str(e))
        raise SystemExit(1)


def cmd_status(args):
    deploy = importlib.import_module("deploy")
    ui_mod = importlib.import_module("cli_ui")
    ui_mod.banner("服务状态", "sing-box & WARP 健康检查")
    deploy.show_status()


def cmd_update(args):
    ui_mod = importlib.import_module("cli_ui")
    installer = importlib.import_module("installer")
    ui_mod.banner("更新 sing-box", "检查并安装最新版本")
    try:
        installer.require_root()
        installer.ensure_singbox()
        ui_mod.success("sing-box 更新完成")
    except RuntimeError as e:
        ui_mod.error(str(e))
        raise SystemExit(1)


def cmd_cleanup_dns(args):
    deploy = importlib.import_module("deploy")
    cf_dns = importlib.import_module("cloudflare_dns")
    ui_mod = importlib.import_module("cli_ui")
    ui_mod.banner("清理 DNS 记录", "删除所有由本工具创建的 Cloudflare A 记录")
    try:
        cf_token, cf_zone_id = deploy.resolve_cf_dns_credentials()
        removed = cf_dns.cleanup_all_managed_records(cf_zone_id, cf_token)
        ui_mod.success(f"已清理 {removed} 条托管 DNS 记录")
    except RuntimeError as e:
        ui_mod.error(str(e))
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Sing-box 自动部署工具",
    )
    sub = parser.add_subparsers(dest="command")

    p_deploy = sub.add_parser("deploy", help="完整部署 (安装依赖 + 生成配置 + 启动)")
    p_deploy.add_argument("--protocols", type=str, default=None,
                          help="启用的协议 (逗号分隔, 如 anytls,tuic,hy2)")
    p_deploy.add_argument("--domain", type=str, default=None, help="主域名")
    p_deploy.set_defaults(func=cmd_deploy)

    p_install = sub.add_parser("install", help="仅安装依赖 (WARP, sing-box)")
    p_install.set_defaults(func=cmd_install)

    p_config = sub.add_parser("config", help="重新生成并应用配置 (使用已保存的状态)")
    p_config.add_argument("--protocols", type=str, default=None,
                          help="启用的协议 (逗号分隔)")
    p_config.set_defaults(func=cmd_config)

    p_export = sub.add_parser("export", help="导出客户端配置")
    p_export.add_argument("--format", choices=["json", "link", "qr"], default="json",
                          help="导出格式 (默认 json)")
    p_export.add_argument("--output", type=str, default=None,
                          help="输出文件路径 (仅 json 格式)")
    p_export.set_defaults(func=cmd_export)

    p_status = sub.add_parser("status", help="检查服务状态")
    p_status.set_defaults(func=cmd_status)

    p_update = sub.add_parser("update", help="更新 sing-box 到最新版本")
    p_update.set_defaults(func=cmd_update)

    p_cleanup = sub.add_parser("cleanup-dns", help="删除所有由本工具创建的 Cloudflare DNS 记录")
    p_cleanup.set_defaults(func=cmd_cleanup_dns)

    return parser


if __name__ == "__main__":
    if should_refresh_from_remote():
        ui.banner("Bootstrap", "从远程刷新部署脚本")
        refresh_required_files()
    else:
        ui.info("检测到本地仓库，跳过远程刷新")

    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        # Backward compatible: no subcommand = deploy
        deploy = importlib.import_module("deploy")
        raise SystemExit(deploy.main())

    args.func(args)
