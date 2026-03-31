import os
import re
import select
import shlex
import subprocess
import time
import json  # 新增：用于解析 GitHub API 响应

import cli_ui as ui

WARP_SERVICE = "warp-svc"
LEGACY_WARP_SERVICES = ("warp-go",)
SINGBOX_SERVICE = "sing-box"
SINGBOX_SERVICE_UNIT_PATH = f"/etc/systemd/system/{SINGBOX_SERVICE}.service"
WARP_PROXY_HOST = "127.0.0.1"
WARP_PROXY_PORT = 40000
WARP_PROXY_URL = f"socks5h://{WARP_PROXY_HOST}:{WARP_PROXY_PORT}"
WARP_TRACE_URL = "https://www.cloudflare.com/cdn-cgi/trace"
WARP_APT_KEYRING = "/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg"
WARP_APT_SOURCE = "/etc/apt/sources.list.d/cloudflare-client.list"
WARP_YUM_REPO = "/etc/yum.repos.d/cloudflare-warp.repo"
SYSTEM_RESOLV_CONF = "/etc/resolv.conf"
SYSTEM_RESOLV_BACKUP = "/etc/resolv.conf.singbox-backup"
SYSTEM_DNS_SERVERS = ("1.1.1.1", "1.0.0.1")
WARP_CLI_TIMEOUT = 20
WARP_CONNECT_TIMEOUT = 30
WARP_SERVICE_READY_TIMEOUT = 15

# 原有的 SINGBOX_VERSION 已删除，改为动态获取
SINGBOX_ARCH_MAP = {
    "x86_64": "amd64",
    "amd64": "amd64",
    "aarch64": "arm64",
    "arm64": "arm64",
    "i386": "386",
    "i686": "386",
    "armv7l": "armv7",
    "armv6l": "armv6",
    "armv5l": "armv5",
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

def run_cmd(cmd, timeout=1800):
    ui.command(cmd)
    proc = subprocess.Popen(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    lines = []
    start = time.time()
    last_log = start
    assert proc.stdout is not None
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

        if proc.poll() is not None:
            break

        now = time.time()
        elapsed = int(now - start)
        if now - last_log >= 1:
            print(
                "\r"
                + ui.status_text("WAIT", f"{spinner[spin_idx % len(spinner)]} command running... {elapsed}s"),
                end="",
                flush=True,
            )
            spin_idx += 1
            last_log = now
        if now - start > timeout:
            proc.kill()
            print("\r" + " " * 80 + "\r", end="", flush=True)
            raise RuntimeError(f"command timeout after {timeout}s: {cmd}")

    output = "".join(lines).strip()
    print("\r" + " " * 80 + "\r", end="", flush=True)
    if proc.returncode != 0:
        tail = "\n".join(output.splitlines()[-20:])
        raise RuntimeError(f"command failed: {cmd}\n{tail}")
    return output

def command_exists(name):
    result = subprocess.run(
        f"command -v {name} >/dev/null 2>&1",
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    return result.returncode == 0

def require_root():
    uid = subprocess.run("id -u", shell=True, stdout=subprocess.PIPE, text=True, check=True).stdout.strip()
    if uid != "0":
        raise RuntimeError("请使用 root 运行")

def fetch_latest_singbox_version():
    """从 GitHub API 获取最新的正式版版本号"""
    ui.info("正在检查 GitHub 上 sing-box 的最新版本...")
    api_url = "https://api.github.com/repos/SagerNet/sing-box/releases/latest"
    try:
        # 使用 curl 获取，避免在某些环境下缺少 python requests 库
        res = subprocess.run(
            ["curl", "-fsSL", api_url],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10
        )
        if res.returncode != 0:
            return None
        data = json.loads(res.stdout)
        tag = data.get("tag_name", "")
        return tag.lstrip('v') # 返回 1.11.0 这种格式
    except Exception as e:
        ui.warning(f"无法获取最新版本信息: {e}")
        return None

def install_singbox(version):
    """根据指定的版本号下载并安装"""
    arch = resolve_singbox_arch()
    release_tag = f"v{version}"
    asset = f"sing-box-{version}-linux-{arch}.tar.gz"
    download_url = f"https://github.com/SagerNet/sing-box/releases/download/{release_tag}/{asset}"
    
    extract_dir = run_cmd("mktemp -d").strip()
    archive_path = os.path.join(extract_dir, asset)
    package_dir = os.path.join(extract_dir, f"sing-box-{version}-linux-{arch}")
    binary_path = os.path.join(package_dir, "sing-box")

    ui.info(f"正在下载并安装 sing-box {release_tag}...")
    run_cmd(f"curl -fsSL -o {shlex.quote(archive_path)} {shlex.quote(download_url)}")
    run_cmd(f"tar -xzf {shlex.quote(archive_path)} -C {shlex.quote(extract_dir)}")
    
    if not os.path.isfile(binary_path):
        raise RuntimeError(f"下载包中未找到可执行文件: {binary_path}")

    # 安装前先停止服务，防止 Text file busy
    if warp_active(SINGBOX_SERVICE):
        run_cmd(f"systemctl stop {SINGBOX_SERVICE}")

    run_cmd(f"install -m 755 {shlex.quote(binary_path)} /usr/bin/sing-box")
    ui.success(f"sing-box {release_tag} 部署成功")

def get_singbox_version(binary_path=None):
    path = binary_path or resolve_singbox_path()
    if not path:
        return None
    try:
        result = subprocess.run(
            [path, "version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        first_line = result.stdout.splitlines()[0].strip() if result.stdout else ""
        match = re.search(r"sing-box version\s+(.+)", first_line)
        return match.group(1).strip() if match else None
    except:
        return None

def ensure_singbox():
    latest_v = fetch_latest_singbox_version()
    current_v = get_singbox_version()

    if not latest_v:
        if current_v:
            ui.warning("由于无法连接 GitHub，将维持当前本地版本")
            ensure_singbox_service()
            return
        else:
            raise RuntimeError("无法获取最新版本且本地未安装 sing-box，请检查网络")

    if not current_v:
        ui.step(f"检测到未安装 sing-box，开始安装最新版 {latest_v}")
        install_singbox(latest_v)
    elif current_v != latest_v:
        ui.warning(f"检测到新版本: {current_v} -> {latest_v}，开始执行自动更新")
        install_singbox(latest_v)
    else:
        ui.success(f"sing-box 已是最新版本 ({current_v})")

    ensure_singbox_service()

def ensure_singbox_service():
    if not os.path.isfile(SINGBOX_SERVICE_UNIT_PATH):
        ui.step(f"写入 sing-box systemd unit")
        with open(SINGBOX_SERVICE_UNIT_PATH, "w", encoding="utf-8") as f:
            f.write(SINGBOX_SYSTEMD_UNIT)
        run_cmd("systemctl daemon-reload")
    run_cmd(f"systemctl enable {SINGBOX_SERVICE}")

def resolve_singbox_path():
    result = subprocess.run("command -v sing-box", shell=True, stdout=subprocess.PIPE, text=True)
    return result.stdout.strip() or None

def resolve_singbox_arch():
    machine = os.uname().machine.lower()
    arch = SINGBOX_ARCH_MAP.get(machine)
    if arch: return arch
    raise RuntimeError(f"暂不支持当前 CPU 架构: {machine}")

def warp_active(service):
    res = subprocess.run(f"systemctl is-active {service}", shell=True, stdout=subprocess.PIPE, text=True)
    return res.stdout.strip() == "active"

# ... (保留你脚本中其他的 ensure_dependencies, warp_proxy_ready 等函数不变) ...

def ensure_dependencies():
    require_root()
    # ensure_system_cloudflare_dns() # 如果需要可以保留
    # ensure_ss_tool() # 如果需要可以保留
    
    # 核心安装逻辑
    ensure_singbox()
    
    # 其他检查
    # ensure_warp() 
    # ensure_port_safety()
    return "completed"

if __name__ == "__main__":
    ui.banner("依赖自检与更新", "自动检查最新版 sing-box")
    try:
        ensure_dependencies()
        ui.success("所有基础组件已就绪")
    except RuntimeError as e:
        ui.error(str(e))
        raise SystemExit(1)