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
from . import certs
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



def cmd_status(args):
    deploy.show_status()

def cmd_doctor(args):
    doctor.run_doctor()

def cmd_validate(args):
    validate.run_validate()

def cmd_benchmark(args):
    benchmark.run_benchmark()

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
        watchdog.deploy_watchdog(deploy.WATCHDOG_SCRIPT_PATH, warp_mode=warp_mode)
        ui.success("Watchdog 守护脚本已部署")
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

def cmd_redeploy(args):
    ui.banner("重新部署", "保留域名和协议，生成全新随机凭据")
    if not ui.confirm("此操作将更新所有配置及凭据，旧客户端配置将失效。是否继续？"):
        ui.info("已取消重新部署。")
        sys.exit(0)
    try:
        protocols = [p.strip() for p in args.protocols.split(",")] if args.protocols else None
        deploy.redeploy(enabled_protocols=protocols)
    except RuntimeError as e:
        ui.error(str(e))
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
        __version__ = "0.2.1" # fallback

    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    
    sub = parser.add_subparsers(dest="command")

    p_deploy = sub.add_parser("deploy", help="完整部署 (安装依赖 + 生成配置 +启动)")
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
    p_export.add_argument("--format", choices=["json", "link"], default="json",
                          help="导出格式 (default: json)")
    p_export.add_argument("--output", type=str, default=None,
                          help="输出文件路径 (仅 json 格式)")
    p_export.set_defaults(func=cmd_export)



    p_status = sub.add_parser("status", help="检查服务状态")
    p_status.set_defaults(func=cmd_status)

    p_doctor = sub.add_parser("doctor", help="运行系统和依赖状态诊断检查")
    p_doctor.set_defaults(func=cmd_doctor)

    p_validate = sub.add_parser("validate", help="校验生成配置语法的正确性")
    p_validate.set_defaults(func=cmd_validate)

    p_benchmark = sub.add_parser("benchmark", help="对代理节点进行速度和延迟测试")
    p_benchmark.set_defaults(func=cmd_benchmark)

    p_update = sub.add_parser("update", help="更新 sing-box 到最新版本")
    p_update.set_defaults(func=cmd_update)

    p_cleanup = sub.add_parser("cleanup-dns", help="删除所有由本工具创建的 Cloudflare DNS 记录")
    p_cleanup.set_defaults(func=cmd_cleanup_dns)

    p_certs = sub.add_parser("certs", help="手动管理/续签 TLS 证书")
    p_certs.set_defaults(func=cmd_certs)

    p_watchdog = sub.add_parser("watchdog", help="手动部署/更新 WARP Watchdog 守护脚本")
    p_watchdog.set_defaults(func=cmd_watchdog)

    p_uninstall = sub.add_parser("uninstall", help="完整卸载工具部署的所有组件")
    p_uninstall.add_argument("--remove-warp", action="store_true", help="同时卸载 WARP (cloudflare-warp 软件包)")
    p_uninstall.set_defaults(func=cmd_uninstall)

    p_redeploy = sub.add_parser("redeploy", help="保留域名，重新生成全部凭据并重新部署")
    p_redeploy.add_argument("--protocols", type=str, default=None,
                            help="覆盖原状态的协议列表 (逗号分隔)")
    p_redeploy.set_defaults(func=cmd_redeploy)

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
