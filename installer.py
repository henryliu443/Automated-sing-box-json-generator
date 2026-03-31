import os
import re
import select
import shlex
import subprocess
import time

import cli_ui as ui

WARP_SERVICE = "warp-svc"
LEGACY_WARP_SERVICES = ("warp-go",)
SINGBOX_SERVICE = "sing-box"
SINGBOX_SERVICE_UNIT_PATH = f"/etc/systemd/system/{SINGBOX_SERVICE}.service"
SINGBOX_VERSION = "1.13.0-beta.7"
WARP_PROXY_PORT = 40000

PROTOCOL_PORTS = (23244, 7443, 9443)
PROXY_MODE = "proxy"
TUN_MODE = "tun"

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
        if now - last_log >= 1:
            print(
                f"\r{ui.status_text('WAIT', f'{spinner[spin_idx % 4]} 正在执行... {int(now - start)}s')}",
                end="",
                flush=True,
            )
            spin_idx += 1
            last_log = now

        if now - start > timeout:
            proc.kill()
            raise RuntimeError(f"命令超时: {cmd}")

    print("\r" + " " * 80 + "\r", end="", flush=True)
    if proc.returncode != 0:
        raise RuntimeError(f"命令失败: {cmd}")
    return "".join(lines).strip()


def command_exists(name):
    return (
        subprocess.run(
            ["sh", "-lc", f"command -v {shlex.quote(name)}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )


def require_root():
    if os.getuid() != 0:
        raise RuntimeError("请使用 root 运行")


def service_is_active(service):
    res = subprocess.run(
        ["systemctl", "is-active", service],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    return res.stdout.strip() == "active"


def ensure_ss_tool():
    if command_exists("ss"):
        return
    if command_exists("apt-get"):
        run_cmd("apt-get update && apt-get install -y iproute2")
        return
    if command_exists("yum"):
        run_cmd("yum install -y iproute")
        return
    if command_exists("dnf"):
        run_cmd("dnf install -y iproute")
        return
    raise RuntimeError("未检测到 ss，且无法自动安装 iproute")


def print_port_snapshot():
    ensure_ss_tool()
    ui.info("当前系统端口监听快照:")
    run_cmd("ss -lntup")


def _run_capture(args, timeout=15):
    return subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
    )


def _warp_cli(*args):
    return _run_capture(["warp-cli", "--accept-tos", "--no-ansi", *args])


def _try_warp_cli(*args):
    try:
        return _warp_cli(*args).returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _parse_port(local_address):
    if ":" not in local_address:
        return None
    try:
        return int(local_address.rsplit(":", 1)[1])
    except ValueError:
        return None


def _list_listeners():
    ensure_ss_tool()
    result = _run_capture(["ss", "-lntupH"])
    if result.returncode != 0:
        raise RuntimeError("无法获取端口监听信息")

    listeners = {}
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue

        port = _parse_port(parts[4])
        if port is None:
            continue

        listeners.setdefault(port, []).append(
            {
                "line": line,
                "processes": re.findall(r'"([^"]+)"', line),
            }
        )
    return listeners


def _port_owners(port, listeners):
    entries = listeners.get(port, [])
    owners = set()
    for entry in entries:
        owners.update(entry["processes"])
    return owners


def _wait_for_port(port, timeout=12):
    deadline = time.time() + timeout
    while time.time() < deadline:
        listeners = _list_listeners()
        if port in listeners:
            return True
        time.sleep(1)
    return False


def _expected_port_owners(warp_mode):
    expected = {port: {SINGBOX_SERVICE} for port in PROTOCOL_PORTS}
    if warp_mode == PROXY_MODE:
        expected[WARP_PROXY_PORT] = {WARP_SERVICE, "warp-cli", *LEGACY_WARP_SERVICES}
    return expected


def ensure_port_safety(warp_mode=PROXY_MODE, require_runtime=False):
    if warp_mode not in {PROXY_MODE, TUN_MODE}:
        raise RuntimeError(f"不支持的 WARP 模式: {warp_mode}")

    listeners = _list_listeners()
    expected = _expected_port_owners(warp_mode)

    errors = []
    for port, allowed_owners in expected.items():
        owners = _port_owners(port, listeners)

        if not owners:
            if require_runtime:
                errors.append(f"端口 {port} 未监听")
            continue

        unexpected = owners - allowed_owners
        if unexpected:
            errors.append(f"端口 {port} 被非预期进程占用: {', '.join(sorted(unexpected))}")
            continue

        if require_runtime and port in PROTOCOL_PORTS and SINGBOX_SERVICE not in owners:
            errors.append(f"端口 {port} 未由 {SINGBOX_SERVICE} 接管")

    if errors:
        raise RuntimeError("；".join(errors))

    ui.success("端口安全检查通过")


def get_singbox_version():
    path = subprocess.run(
        ["sh", "-lc", "command -v sing-box"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    ).stdout.strip()
    if not path:
        return None

    try:
        res = subprocess.run([path, "version"], stdout=subprocess.PIPE, text=True, check=False)
    except OSError:
        return None

    first_line = res.stdout.splitlines()[0] if res.stdout else ""
    match = re.search(r"sing-box version\s+(.+)", first_line)
    return match.group(1).strip() if match else None


def install_singbox(version):
    machine = os.uname().machine.lower()
    arch = SINGBOX_ARCH_MAP.get(machine)
    if not arch:
        raise RuntimeError(f"不支持的架构: {machine}")

    release_tag = f"v{version}"
    asset = f"sing-box-{version}-linux-{arch}.tar.gz"
    url = f"https://github.com/SagerNet/sing-box/releases/download/{release_tag}/{asset}"

    tmp_dir = run_cmd("mktemp -d").strip()
    quoted_tmp_dir = shlex.quote(tmp_dir)
    quoted_asset = shlex.quote(asset)
    quoted_url = shlex.quote(url)

    run_cmd(f"curl -fsSL -o {quoted_tmp_dir}/{quoted_asset} {quoted_url}")
    run_cmd(f"tar -xzf {quoted_tmp_dir}/{quoted_asset} -C {quoted_tmp_dir}")

    binary = f"{tmp_dir}/sing-box-{version}-linux-{arch}/sing-box"
    if service_is_active(SINGBOX_SERVICE):
        run_cmd(f"systemctl stop {SINGBOX_SERVICE}")
    run_cmd(f"install -m 755 {shlex.quote(binary)} /usr/bin/sing-box")
    ui.success(f"已安装/更新至版本: {release_tag}")


def ensure_singbox_service():
    if not os.path.exists(SINGBOX_SERVICE_UNIT_PATH):
        with open(SINGBOX_SERVICE_UNIT_PATH, "w", encoding="utf-8") as f:
            f.write(SINGBOX_SYSTEMD_UNIT)
        run_cmd("systemctl daemon-reload")

    run_cmd(f"systemctl enable {SINGBOX_SERVICE}")


def ensure_singbox():
    current = get_singbox_version()
    if current != SINGBOX_VERSION:
        ui.info(f"同步 sing-box 版本: {current or '未安装'} -> {SINGBOX_VERSION}")
        install_singbox(SINGBOX_VERSION)
    else:
        ui.success(f"sing-box 版本符合预期 ({current})")

    ensure_singbox_service()


def _ensure_warp_installed():
    if command_exists("warp-cli") and command_exists(WARP_SERVICE):
        return
    raise RuntimeError("未检测到官方 Cloudflare WARP，请先安装 cloudflare-warp（warp-svc / warp-cli）")


def _ensure_warp_service_running():
    if service_is_active(WARP_SERVICE):
        return
    ui.step(f"启动 {WARP_SERVICE}")
    run_cmd(f"systemctl enable --now {WARP_SERVICE}")


def _detect_proxy_mode():
    owners = _port_owners(WARP_PROXY_PORT, _list_listeners())
    return bool(owners & {WARP_SERVICE, "warp-cli", *LEGACY_WARP_SERVICES})


def _try_enable_proxy_mode():
    ui.step("尝试初始化 WARP 本地代理模式")
    _try_warp_cli("disconnect")
    if not (_try_warp_cli("mode", "proxy") or _try_warp_cli("set-mode", "proxy")):
        return False
    if not (_try_warp_cli("proxy", "port", str(WARP_PROXY_PORT)) or _try_warp_cli("set-proxy-port", str(WARP_PROXY_PORT))):
        return False
    _try_warp_cli("connect")
    return _wait_for_port(WARP_PROXY_PORT)


def detect_warp_mode():
    _ensure_warp_installed()
    _ensure_warp_service_running()

    if _detect_proxy_mode():
        ui.success(f"检测到 WARP 本地代理模式 (127.0.0.1:{WARP_PROXY_PORT})")
        return PROXY_MODE

    if _try_enable_proxy_mode():
        ui.success(f"已启用 WARP 本地代理模式 (127.0.0.1:{WARP_PROXY_PORT})")
        return PROXY_MODE

    ui.warning("未检测到 WARP 本地代理监听，回退按系统隧道模式处理")
    return TUN_MODE


def ensure_dependencies():
    require_root()
    ensure_singbox()
    warp_mode = detect_warp_mode()
    ensure_port_safety(warp_mode)
    return warp_mode
