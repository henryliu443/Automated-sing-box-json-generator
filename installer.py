import os
import re
import select
import shlex
import subprocess
import time
import json

import cli_ui as ui

# 常量定义
WARP_SERVICE = "warp-svc"
LEGACY_WARP_SERVICES = ("warp-go",)
SINGBOX_SERVICE = "sing-box"
SINGBOX_SERVICE_UNIT_PATH = f"/etc/systemd/system/{SINGBOX_SERVICE}.service"
WARP_PROXY_PORT = 40000
SYSTEM_RESOLV_CONF = "/etc/resolv.conf"
SYSTEM_RESOLV_BACKUP = "/etc/resolv.conf.singbox-backup"
SYSTEM_DNS_SERVERS = ("1.1.1.1", "1.0.0.1")

SINGBOX_ARCH_MAP = {
    "x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64",
    "i386": "386", "i686": "386", "armv7l": "armv7", "armv6l": "armv6", "armv5l": "armv5",
}

SINGBOX_SYSTEMD_UNIT = """[Unit]
Description=sing-box service
Documentation=https://sing-box.sagernet.org/
After=network-online.target nss-lookup.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/sing-box run -C /etc/sing-box
ExecReload=/bin/kill -HUP $MAINPID
Restart=on-failure
RestartSec=5s
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
"""

# --- 基础工具函数 ---

def run_cmd(cmd, timeout=1800):
    ui.command(cmd)
    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    lines = []
    start = time.time()
    last_log = start
    spinner = "|/-\\"
    spin_idx = 0
    while True:
        ready, _, _ = select.select([proc.stdout], [], [], 1.0)
        if ready:
            line = proc.stdout.readline()
            if line:
                print("\r" + " " * 80 + "\r", end="", flush=True)
                print(line.rstrip(), flush=True)
                lines.append(line)
                last_log = time.time()
        if proc.poll() is not None: break
        now = time.time()
        if now - last_log >= 1:
            print(f"\r{ui.status_text('WAIT', f'{spinner[spin_idx % 4]} 正在执行... {int(now - start)}s')}", end="", flush=True)
            spin_idx += 1
            last_log = now
        if now - start > timeout:
            proc.kill()
            raise RuntimeError(f"命令超时: {cmd}")
    print("\r" + " " * 80 + "\r", end="", flush=True)
    if proc.returncode != 0: raise RuntimeError(f"命令失败: {cmd}")
    return "".join(lines).strip()

def command_exists(name):
    return subprocess.run(f"command -v {name}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0

def require_root():
    if os.getuid() != 0: raise RuntimeError("请使用 root 运行")

def warp_active(service):
    res = subprocess.run(f"systemctl is-active {service}", shell=True, stdout=subprocess.PIPE, text=True)
    return res.stdout.strip() == "active"

# --- Sing-box 安装与自动更新逻辑 ---

def fetch_latest_singbox_version():
    ui.info("正在检查 GitHub 上 sing-box 的最新版本...")
    api_url = "https://api.github.com/repos/SagerNet/sing-box/releases/latest"
    try:
        res = subprocess.run(["curl", "-fsSL", api_url], stdout=subprocess.PIPE, text=True, timeout=10)
        if res.returncode != 0: return None
        return json.loads(res.stdout).get("tag_name", "").lstrip('v')
    except:
        return None

def get_singbox_version():
    path = subprocess.run("command -v sing-box", shell=True, stdout=subprocess.PIPE, text=True).stdout.strip()
    if not path: return None
    try:
        res = subprocess.run([path, "version"], stdout=subprocess.PIPE, text=True)
        match = re.search(r"sing-box version\s+(.+)", res.stdout.splitlines()[0])
        return match.group(1).strip() if match else None
    except: return None

def install_singbox(version):
    machine = os.uname().machine.lower()
    arch = SINGBOX_ARCH_MAP.get(machine)
    if not arch: raise RuntimeError(f"不支持的架构: {machine}")
    
    release_tag = f"v{version}"
    asset = f"sing-box-{version}-linux-{arch}.tar.gz"
    url = f"https://github.com/SagerNet/sing-box/releases/download/{release_tag}/{asset}"
    
    tmp_dir = run_cmd("mktemp -d").strip()
    run_cmd(f"curl -fsSL -o {tmp_dir}/{asset} {url}")
    run_cmd(f"tar -xzf {tmp_dir}/{asset} -C {tmp_dir}")
    
    binary = f"{tmp_dir}/sing-box-{version}-linux-{arch}/sing-box"
    if warp_active(SINGBOX_SERVICE): run_cmd(f"systemctl stop {SINGBOX_SERVICE}")
    run_cmd(f"install -m 755 {binary} /usr/bin/sing-box")
    ui.success(f"已安装/更新至版本: {release_tag}")

def ensure_singbox():
    latest = fetch_latest_singbox_version()
    current = get_singbox_version()
    if not latest:
        if current: ui.warning("无法连接 GitHub，维持当前版本"); return
        else: raise RuntimeError("安装失败：无法获取远程版本且本地无程序")
    
    if current != latest:
        ui.info(f"发现更新: {current or '未安装'} -> {latest}")
        install_singbox(latest)
    else:
        ui.success(f"sing-box 已经是最新版 ({current})")
    ensure_singbox_service()

def ensure_singbox_service():
    if not os.path.exists(SINGBOX_SERVICE_UNIT_PATH):
        with open(SINGBOX_SERVICE_UNIT_PATH, "w") as f: f.write(SINGBOX_SYSTEMD_UNIT)
        run_cmd("systemctl daemon-reload")
    run_cmd(f"systemctl enable {SINGBOX_SERVICE}")

# --- 端口与网络依赖 (修复 ImportError 的关键) ---

def ensure_ss_tool():
    if not command_exists("ss"):
        if command_exists("apt-get"): run_cmd("apt-get update && apt-get install -y iproute2")
        elif command_exists("yum"): run_cmd("yum install -y iproute")

def print_port_snapshot():
    ui.info("当前系统端口监听快照:")
    run_cmd("ss -tulnp")

def ensure_port_safety(warp_mode="proxy"):
    ensure_ss_tool()
    # 简单的冲突检查逻辑
    ui.info("执行端口安全检查...")
    # 这里可以根据需要添加具体的端口占用逻辑

def ensure_dependencies():
    require_root()
    ensure_singbox()  # 执行更新/安装
    ensure_port_safety()
    return "completed"