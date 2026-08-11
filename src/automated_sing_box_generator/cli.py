import argparse
import os
import sys
import subprocess
import urllib.request
import json

from . import ui
from . import deploy
from . import config as cfg
from . import installer
from . import export
from . import cloudflare_dns as cf_dns
from . import watchdog
from . import state as state_mod
from . import doctor
from . import validate
from . import benchmark

def check_tool_update():
    """检查本项目在 GitHub 上是否有更新"""
    try:
        # 获取本地 git commit
        res = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=1)
        if res.returncode != 0:
            return # 不是 git 仓库或者没安装 git
        local_sha = res.stdout.strip()
        
        # 获取远程最新 commit
        req = urllib.request.Request(
            "https://api.github.com/repos/henryliu443/Automated-sing-box-json-generator/commits/main",
            headers={"User-Agent": "Update-Checker"}
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            remote_sha = data.get("sha", "")
            
        if remote_sha and not remote_sha.startswith(local_sha):
            ui.warning("检测到工具更新: 发现新版本代码！")
            ui.info("建议运行 `git pull` 获取最新更新。")
    except Exception:
        pass # 忽略网络或检查失败

def _parse_protocols(value):
    if not value:
        return None
    return [p.strip() for p in value.split(",") if p.strip()]

def cmd_deploy(args):
    protocols = _parse_protocols(args.protocols) if args.protocols else None
    domain = args.domain or None
    if getattr(args, "warp_mode", None):
        if args.warp_mode in ("wg", "wireguard"):
            warp_mode = "wireguard"
        elif args.warp_mode == "direct":
            warp_mode = "none"
        else:
            warp_mode = args.warp_mode
        os.environ["WARP_MODE"] = warp_mode
    if getattr(args, "wg_config", None):
        if os.path.isfile(args.wg_config):
            os.environ["WG_CONFIG_FILE"] = args.wg_config
        else:
            os.environ["WG_CONFIG"] = args.wg_config
    fingerprint_overrides = {}
    if args.reality_server:
        fingerprint_overrides[cfg.REALITY_SERVER_ENV] = args.reality_server
    if args.reality_port is not None:
        fingerprint_overrides[cfg.REALITY_PORT_ENV] = str(args.reality_port)
    if args.hy2_masquerade:
        fingerprint_overrides[cfg.HY2_MASQUERADE_ENV] = args.hy2_masquerade
    if args.hy2_up is not None:
        fingerprint_overrides[cfg.HY2_UP_MBPS_ENV] = str(args.hy2_up)
    if args.hy2_down is not None:
        fingerprint_overrides[cfg.HY2_DOWN_MBPS_ENV] = str(args.hy2_down)
    if args.server_ip:
        os.environ["SERVER_IP"] = args.server_ip
    sys.exit(deploy.main(
        enabled_protocols=protocols,
        domain_root=domain,
        fingerprint_overrides=fingerprint_overrides or None
    ))

def cmd_outbound(args):
    from . import outbound as ob
    if args.outbound_cmd == "switch":
        ob.switch_outbound(args.target)
    elif args.outbound_cmd == "status":
        ob.show_outbound_status()
    elif args.outbound_cmd == "add":
        wg_content = None
        if args.outbound_type == "wireguard":
            if getattr(args, "wg_config", None):
                if os.path.isfile(args.wg_config):
                    with open(args.wg_config, 'r', encoding='utf-8') as f:
                        wg_content = f.read().strip()
                else:
                    wg_content = args.wg_config.strip()
            else:
                from .wireguard import read_wg_config_interactive
                wg_content = read_wg_config_interactive()
        ob.add_outbound_profile(args.outbound_type, wg_content=wg_content)
    else:
        ob.show_outbound_status()

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
    if getattr(args, 'api', False):
        ui.banner("重新部署", "保留域名和协议，生成全新随机凭据")
        if not ui.confirm("此操作将更新所有配置及凭据，旧客户端配置将失效。是否继续？"):
            ui.info("已取消重新部署。")
            sys.exit(0)
        try:
            deploy.redeploy(enabled_protocols=protocols)
        except RuntimeError as e:
            ui.error(str(e))
            sys.exit(1)
    else:
        ui.banner("重新生成配置", "基于当前部署状态更新 config.json")
        try:
            deploy.reconfigure(enabled_protocols=protocols)
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



def cmd_doctor(args):
    if getattr(args, 'status', False):
        deploy.show_status()
    elif getattr(args, 'validate', False):
        validate.run_validate()
    elif getattr(args, 'benchmark', False):
        benchmark.run_benchmark()
    else:
        doctor.run_doctor()
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

def cmd_certs(args):
    ui.banner("管理证书", "手动触发 TLS 证书续签")
    try:
        loaded = state_mod.load_state()
        if not loaded:
            raise RuntimeError("未找到部署状态，请先运行 deploy")
        cf_token, cf_zone_id = deploy.resolve_cf_dns_credentials()
        phosts = loaded.get("protocol_hosts", {})
        enabled_protocols = loaded.get("enabled_protocols", None)
        deploy.run_tls_issuance(phosts, cf_token, cf_zone_id, enabled_protocols)
        ui.success("TLS 证书处理完成")
    except RuntimeError as e:
        ui.error(str(e))
        sys.exit(1)

def cmd_watchdog(args):
    ui.banner("部署 Watchdog", "手动部署/更新 WARP 守护脚本")
    try:
        loaded = state_mod.load_state()
        warp_mode = loaded.get("warp_mode", "proxy") if loaded else "proxy"
        if warp_mode == "none":
            ui.info("WARP 为直连模式 (none)，跳过 Watchdog 部署")
            return
        watchdog.deploy_watchdog(deploy.WATCHDOG_SCRIPT_PATH, warp_mode=warp_mode)
        ui.success("Watchdog 守护脚本已部署")
    except RuntimeError as e:
        ui.error(str(e))
        sys.exit(1)


def cmd_firewall(args):
    from . import config as cfg
    from .firewall import deploy_firewall, remove_firewall, firewall_status
    remove = getattr(args, 'remove', False)
    status = getattr(args, 'status', False)
    if remove:
        ui.banner("移除网络加固", "移除 nftables singbox_guard 加固规则")
        try:
            installer.require_root()
            remove_firewall()
        except RuntimeError as e:
            ui.error(str(e))
            sys.exit(1)
    elif status:
        firewall_status()
    else:
        ui.banner("部署网络加固", "配置 nftables OS 网络加固规则")
        try:
            installer.require_root()
            loaded = state_mod.load_state()
            enabled = loaded.get("enabled_protocols") if loaded else None
            pports = cfg.protocol_ports(enabled) if enabled else None
            deploy_firewall(pports)
            ui.success("网络加固规则已部署")
        except RuntimeError as e:
            ui.error(str(e))
            sys.exit(1)

def cmd_uninstall(args):
    ui.banner("警告", "此操作将移除由本工具部署的所有组件 (包括配置、证书、systemd服务、定时任务等)")
    if not ui.confirm("此操作不可恢复，是否继续？"):
        ui.info("已取消卸载。")
        sys.exit(0)
    try:
        from . import uninstall
        uninstall.run_uninstall(remove_warp=args.remove_warp)
    except Exception as e:
        ui.error(f"卸载过程中发生错误: {e}")
        sys.exit(1)

def build_parser():
    parser = argparse.ArgumentParser(
        prog="automated-sing-box-generator",
        description="Sing-box 自动部署工具",
    )
    
    try:
        from importlib.metadata import version
        __version__ = version("automated-sing-box-generator")
    except Exception:
        __version__ = "0.3.21" # fallback

    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    
    sub = parser.add_subparsers(dest="command")

    p_deploy = sub.add_parser("deploy", help="完整部署 (安装依赖 + 生成配置 +启动)")
    p_deploy.add_argument("--protocols", type=str, default=None,
                          help="启用的协议 (逗号分隔, 如 anytls,tuic,hy2)")
    p_deploy.add_argument("--domain", type=str, default=None, help="主域名")
    p_deploy.add_argument("--warp-mode", choices=["proxy", "tun", "direct", "none", "wireguard", "wg"], default=None,
                          help="出站模式 (proxy, tun, direct, none, wireguard)")
    p_deploy.add_argument("--wg-config", type=str, default=None, help="WireGuard 配置内容或文件路径")
    p_deploy.add_argument("--reality-server", type=str, default=None, help="Reality 伪装域名")
    p_deploy.add_argument("--reality-port", type=int, default=None, help="Reality 伪装端口")
    p_deploy.add_argument("--hy2-masquerade", type=str, default=None, help="Hysteria2 masquerade URL")
    p_deploy.add_argument("--hy2-up", type=int, default=None, help="Hysteria2 上行带宽 (Mbps, 默认 50)")
    p_deploy.add_argument("--hy2-down", type=int, default=None, help="Hysteria2 下行带宽 (Mbps, 默认 200)")
    p_deploy.add_argument("--server-ip", type=str, default=None, help="VPS 公网 IP (用于客户端 TUN 排除)")
    p_deploy.set_defaults(func=cmd_deploy)

    p_install = sub.add_parser("install", help="仅安装依赖 (WARP, sing-box)")
    p_install.set_defaults(func=cmd_install)

    p_config = sub.add_parser("config", help="管理配置和凭据")
    p_config.add_argument("--protocols", type=str, default=None,
                          help="覆盖原状态的协议列表 (逗号分隔)")
    p_config.add_argument("--api", action="store_true", help="重新生成全部凭据并重新部署 (等同于旧版 redeploy)")
    p_config.set_defaults(func=cmd_config)

    p_export = sub.add_parser("export", help="导出客户端配置")
    p_export.add_argument("--format", choices=["json", "link"], default="json",
                          help="导出格式 (default: json)")
    p_export.add_argument("--output", type=str, default=None,
                          help="输出文件路径 (仅 json 格式)")
    p_export.set_defaults(func=cmd_export)

    p_doctor = sub.add_parser("doctor", help="系统诊断与状态检查")
    p_doctor.add_argument("--status", action="store_true", help="检查服务运行状态")
    p_doctor.add_argument("--validate", action="store_true", help="校验生成配置语法的正确性")
    p_doctor.add_argument("--benchmark", action="store_true", help="对代理节点进行速度和延迟测试")
    p_doctor.set_defaults(func=cmd_doctor)

    p_manage = sub.add_parser("manage", help="高级维护工具 (更新、证书、定时任务等)")
    manage_sub = p_manage.add_subparsers(dest="manage_cmd")
    
    p_update = manage_sub.add_parser("update", help="更新 sing-box 到最新版本")
    p_update.set_defaults(func=cmd_update)
    
    p_certs = manage_sub.add_parser("certs", help="手动管理/续签 TLS 证书")
    p_certs.set_defaults(func=cmd_certs)
    
    p_watchdog = manage_sub.add_parser("watchdog", help="手动部署/更新 WARP Watchdog 守护脚本")
    p_watchdog.set_defaults(func=cmd_watchdog)
    
    p_cleanup = manage_sub.add_parser("cleanup-dns", help="删除所有由本工具创建的 Cloudflare DNS 记录")
    p_cleanup.set_defaults(func=cmd_cleanup_dns)

    p_firewall = manage_sub.add_parser("firewall", help="管理 OS 网络加固 (nftables)")
    p_firewall.add_argument("--remove", action="store_true", help="移除加固规则")
    p_firewall.add_argument("--status", action="store_true", help="查看当前加固状态")
    p_firewall.set_defaults(func=cmd_firewall)

    p_outbound = manage_sub.add_parser("outbound", help="管理出站出口 (即时切换 WARP / WireGuard / 直连)")
    p_outbound.set_defaults(func=cmd_outbound)
    outbound_sub = p_outbound.add_subparsers(dest="outbound_cmd")

    p_switch = outbound_sub.add_parser("switch", help="切换活跃出口")
    p_switch.add_argument("target", choices=["warp", "wireguard", "direct"])

    outbound_sub.add_parser("status", help="查看当前出口和可用 profile")

    p_ob_add = outbound_sub.add_parser("add", help="添加 / 更新出口 profile")
    p_ob_add.add_argument("outbound_type", choices=["warp", "wireguard"])
    p_ob_add.add_argument("--wg-config", type=str, default=None, help="WireGuard 配置内容或文件路径")

    p_uninstall = sub.add_parser("uninstall", help="完整卸载工具部署的所有组件")
    p_uninstall.add_argument("--remove-warp", action="store_true", help="同时卸载 WARP (cloudflare-warp 软件包)")
    p_uninstall.set_defaults(func=cmd_uninstall)

    return parser

def main():
    check_tool_update()
    
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        sys.exit(deploy.main())

    args.func(args)

if __name__ == "__main__":
    main()
