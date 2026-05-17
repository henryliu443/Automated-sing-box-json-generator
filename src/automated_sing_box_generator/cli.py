import argparse
import os
import sys

from . import ui
from . import deploy
from . import config as cfg
from . import installer
from . import killswitch
from . import export
from . import cloudflare_dns as cf_dns

def _parse_protocols(value):
    if not value:
        return None
    return [p.strip() for p in value.split(",") if p.strip()]

def cmd_deploy(args):
    protocols = _parse_protocols(args.protocols) if args.protocols else None
    domain = args.domain or None
    fingerprint_overrides = {}
    if args.reality_server:
        fingerprint_overrides[cfg.REALITY_SERVER_ENV] = args.reality_server
    if args.reality_port is not None:
        fingerprint_overrides[cfg.REALITY_PORT_ENV] = str(args.reality_port)
    if args.hy2_masquerade:
        fingerprint_overrides[cfg.HY2_MASQUERADE_ENV] = args.hy2_masquerade
    if args.server_ip:
        os.environ["SERVER_IP"] = args.server_ip
    sys.exit(deploy.main(
        enabled_protocols=protocols,
        domain_root=domain,
        fingerprint_overrides=fingerprint_overrides or None
    ))

def cmd_install(args):
    ui.banner("安装依赖", "安装 sing-box, warp-cli 等系统组件")
    try:
        installer.ensure_dependencies()
        ui.success("依赖安装完成")
    except RuntimeError as e:
        ui.error(str(e))
        sys.exit(1)

def cmd_config(args):
    protocols = _parse_protocols(args.protocols) if args.protocols else None
    ui.banner("重新生成配置", "基于当前部署状态更新 config.json")
    try:
        deploy.regenerate_config(enabled_protocols=protocols)
        ui.success("配置重新生成并已应用")
    except RuntimeError as e:
        ui.error(str(e))
        sys.exit(1)

def cmd_export(args):
    ui.banner("导出配置", f"格式: {args.format}")
    try:
        export.export_client_config(fmt=args.format, output=args.output)
    except RuntimeError as e:
        ui.error(str(e))
        sys.exit(1)

def cmd_status(args):
    deploy.show_status()

def cmd_vpn(args):
    try:
        if args.action == "install":
            ui.banner("VPN Kill Switch", "安装 vpnctl 与 nftables 独立规则")
            killswitch.deploy_killswitch_assets()
            return

        if not os.path.isfile(killswitch.VPNCTL_PATH):
            raise RuntimeError("vpnctl 尚未安装，请先运行: automated-sing-box-generator vpn install")

        os.execv(killswitch.VPNCTL_PATH, [killswitch.VPNCTL_PATH, args.action])
    except RuntimeError as e:
        ui.error(str(e))
        sys.exit(1)

def cmd_update(args):
    ui.banner("更新 sing-box", "检查并安装最新版本")
    try:
        installer.require_root()
        installer.ensure_singbox()
        ui.success("sing-box 更新完成")
    except RuntimeError as e:
        ui.error(str(e))
        sys.exit(1)

def cmd_cleanup_dns(args):
    ui.banner("清理 DNS 记录", "删除所有由本工具创建的 Cloudflare A 记录")
    try:
        cf_token, cf_zone_id = deploy.resolve_cf_dns_credentials()
        removed = cf_dns.cleanup_all_managed_records(cf_zone_id, cf_token)
        ui.success(f"已清理 {removed} 条托管 DNS 记录")
    except RuntimeError as e:
        ui.error(str(e))
        sys.exit(1)

def build_parser():
    parser = argparse.ArgumentParser(
        prog="automated-sing-box-generator",
        description="Sing-box 自动部署工具",
    )
    sub = parser.add_subparsers(dest="command")

    p_deploy = sub.add_parser("deploy", help="完整部署 (安装依赖 + 生成配置 + 启动)")
    p_deploy.add_argument("--protocols", type=str, default=None,
                          help="启用的协议 (逗号分隔, 如 anytls,tuic,hy2)")
    p_deploy.add_argument("--domain", type=str, default=None, help="主域名")
    p_deploy.add_argument("--reality-server", type=str, default=None, help="Reality 伪装域名")
    p_deploy.add_argument("--reality-port", type=int, default=None, help="Reality 伪装端口")
    p_deploy.add_argument("--hy2-masquerade", type=str, default=None, help="Hysteria2 masquerade URL")
    p_deploy.add_argument("--server-ip", type=str, default=None, help="VPS 公网 IP (用于客户端 TUN 排除)")
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

    p_vpn = sub.add_parser("vpn", help="管理 VPS VPN ON/OFF kill switch")
    p_vpn.add_argument("action", choices=["install", "on", "off", "status", "refresh"],
                        help="install 安装控制脚本；on/off/status/refresh 调用 vpnctl")
    p_vpn.set_defaults(func=cmd_vpn)

    p_update = sub.add_parser("update", help="更新 sing-box 到最新版本")
    p_update.set_defaults(func=cmd_update)

    p_cleanup = sub.add_parser("cleanup-dns", help="删除所有由本工具创建的 Cloudflare DNS 记录")
    p_cleanup.set_defaults(func=cmd_cleanup_dns)

    return parser

def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        sys.exit(deploy.main())

    args.func(args)

if __name__ == "__main__":
    main()
