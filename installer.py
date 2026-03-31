import os
import re
import select
import subprocess
import time

import cli_ui as ui

WARP_SERVICE = "warp-svc"
LEGACY_WARP_SERVICES = ("warp-go",)
WARP_PROXY_HOST = "127.0.0.1"
WARP_PROXY_PORT = 40000
WARP_PROXY_URL = f"socks5h://{WARP_PROXY_HOST}:{WARP_PROXY_PORT}"
WARP_TRACE_URL = "https://www.cloudflare.com/cdn-cgi/trace"
WARP_APT_KEYRING = "/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg"
WARP_APT_SOURCE = "/etc/apt/sources.list.d/cloudflare-client.list"
WARP_YUM_REPO = "/etc/yum.repos.d/cloudflare-warp.repo"
WARP_CLI_TIMEOUT = 20
WARP_CONNECT_TIMEOUT = 30
WARP_SERVICE_READY_TIMEOUT = 15


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


def ensure_ss_tool():
    if command_exists("ss"):
        return

    ui.step("安装 ss 命令 (iproute2)")
    if command_exists("apt-get"):
        run_cmd("DEBIAN_FRONTEND=noninteractive apt-get update")
        run_cmd("DEBIAN_FRONTEND=noninteractive apt-get install -y iproute2")
    elif command_exists("dnf"):
        run_cmd("dnf install -y iproute")
    elif command_exists("yum"):
        run_cmd("yum install -y iproute")
    else:
        raise RuntimeError("未检测到可用包管理器，无法安装 iproute2(ss)")

    if not command_exists("ss"):
        raise RuntimeError("ss 命令安装失败，无法执行端口冲突检查")


def get_port_owners(port, proto):
    flag = "-ltnp" if proto == "tcp" else "-lunp"
    result = subprocess.run(
        f"ss -H {flag} 'sport = :{port}'",
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    raw = result.stdout.strip()
    owners = set(re.findall(r'\(\("([^"]+)"', raw))
    return owners, raw


def assert_port_allowed(port, proto, allowed_owners):
    owners, raw = get_port_owners(port, proto)
    conflict = owners - set(allowed_owners)
    if conflict:
        raise RuntimeError(
            f"{proto}/{port} 端口被非预期进程占用: {sorted(conflict)}\n"
            f"监听明细:\n{raw or '(empty)'}"
        )


def assert_port_required(port, proto, required_owners):
    owners, raw = get_port_owners(port, proto)
    if not (owners & set(required_owners)):
        raise RuntimeError(
            f"{proto}/{port} 未检测到预期进程监听: {sorted(required_owners)}\n"
            f"监听明细:\n{raw or '(empty)'}"
        )


def print_port_snapshot():
    ui.info("当前端口监听快照 (ss -tulnp)")
    run_cmd("ss -tulnp")


def ensure_port_safety(warp_mode="proxy"):
    ensure_ss_tool()

    # sing-box inbound ports
    assert_port_allowed(23244, "tcp", {"sing-box"})
    assert_port_allowed(7443, "udp", {"sing-box"})
    assert_port_allowed(9443, "udp", {"sing-box"})

    if warp_mode == "proxy":
        # local WARP socks proxy
        allowed = {WARP_SERVICE, *LEGACY_WARP_SERVICES}
        assert_port_allowed(WARP_PROXY_PORT, "tcp", allowed)
        assert_port_required(WARP_PROXY_PORT, "tcp", allowed)


def warp_active(service):
    result = subprocess.run(
        f"systemctl is-active {service}",
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip() == "active"


def trace_reports_warp(cmd):
    result = subprocess.run(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    out = result.stdout
    return result.returncode == 0 and ("warp=on" in out or "warp=plus" in out)


def warp_proxy_ready():
    cmd = f'curl -s --proxy "{WARP_PROXY_URL}" --max-time 6 "{WARP_TRACE_URL}"'
    return trace_reports_warp(cmd)


def warp_tunnel_ready():
    cmd = f'curl -s --max-time 6 "{WARP_TRACE_URL}"'
    return trace_reports_warp(cmd)


def read_os_release():
    data = {}
    if not os.path.isfile("/etc/os-release"):
        return data

    with open("/etc/os-release", "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or "=" not in line:
                continue
            key, value = line.split("=", 1)
            data[key] = value.strip().strip('"')
    return data


def detect_apt_codename():
    info = read_os_release()
    codename = info.get("VERSION_CODENAME") or info.get("UBUNTU_CODENAME")
    if not codename and command_exists("lsb_release"):
        codename = subprocess.run(
            "lsb_release -cs",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.strip()
    if not codename:
        raise RuntimeError("无法识别当前 Debian/Ubuntu 发行版代号，无法配置 Cloudflare WARP 软件源")
    if not re.fullmatch(r"[a-z0-9-]+", codename):
        raise RuntimeError(f"检测到异常发行版代号: {codename}")
    return codename


def ensure_warp_pkg_repo():
    if command_exists("apt-get"):
        codename = detect_apt_codename()
        ui.step("配置 Cloudflare WARP 软件源 (APT)")
        run_cmd("DEBIAN_FRONTEND=noninteractive apt-get update")
        run_cmd("DEBIAN_FRONTEND=noninteractive apt-get install -y curl gnupg")
        run_cmd("install -m 0755 -d /usr/share/keyrings")
        run_cmd(f"curl -fsSL https://pkg.cloudflareclient.com/pubkey.gpg | gpg --yes --dearmor --output {WARP_APT_KEYRING}")
        run_cmd(
            f"printf '%s\\n' "
            f"'deb [signed-by={WARP_APT_KEYRING}] https://pkg.cloudflareclient.com/ {codename} main' "
            f"> {WARP_APT_SOURCE}"
        )
        return "apt-get"

    if command_exists("dnf"):
        ui.step("配置 Cloudflare WARP 软件源 (DNF)")
        run_cmd("dnf install -y curl")
        run_cmd("rpm --import https://pkg.cloudflareclient.com/pubkey.gpg")
        run_cmd(f"curl -fsSL https://pkg.cloudflareclient.com/cloudflare-warp-ascii.repo -o {WARP_YUM_REPO}")
        return "dnf"

    if command_exists("yum"):
        ui.step("配置 Cloudflare WARP 软件源 (YUM)")
        run_cmd("yum install -y curl")
        run_cmd("rpm --import https://pkg.cloudflareclient.com/pubkey.gpg")
        run_cmd(f"curl -fsSL https://pkg.cloudflareclient.com/cloudflare-warp-ascii.repo -o {WARP_YUM_REPO}")
        return "yum"

    raise RuntimeError("未检测到可用包管理器，无法安装官方 Cloudflare WARP (warp-svc)")


def ensure_warp_package():
    if command_exists("warp-cli"):
        ui.success("Cloudflare WARP CLI 已存在")
        return

    pkg_manager = ensure_warp_pkg_repo()
    ui.step("安装 Cloudflare WARP (warp-svc / warp-cli)")
    if pkg_manager == "apt-get":
        run_cmd("DEBIAN_FRONTEND=noninteractive apt-get update")
        run_cmd("DEBIAN_FRONTEND=noninteractive apt-get install -y cloudflare-warp")
    else:
        run_cmd(f"{pkg_manager} install -y cloudflare-warp")

    if not command_exists("warp-cli"):
        raise RuntimeError("cloudflare-warp 安装失败，未检测到 warp-cli")


def warp_cli_cmd(args):
    return f"warp-cli --accept-tos --no-ansi {args}"


def run_warp_cli(args, timeout=WARP_CLI_TIMEOUT, quiet=False, check=True):
    cmd = warp_cli_cmd(args)
    if not quiet:
        ui.command(cmd)

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"warp-cli 命令超时({timeout}s): {cmd}") from e

    output = (result.stdout or "").strip()
    if output and not quiet:
        print(output, flush=True)

    if check and result.returncode != 0:
        detail = f"\n{output}" if output else ""
        raise RuntimeError(f"warp-cli 命令执行失败: {cmd}{detail}")

    return result.returncode, output


def run_compatible_warp_cli(*args_variants, timeout=WARP_CLI_TIMEOUT):
    last_output = ""
    for args in args_variants:
        try:
            returncode, output = run_warp_cli(args, timeout=timeout, check=False)
        except RuntimeError as e:
            last_output = str(e)
            continue
        if returncode == 0:
            return output
        last_output = output or f"exit code {returncode}"

    detail = f"\n{last_output}" if last_output else ""
    raise RuntimeError(f"warp-cli 命令执行失败，已尝试兼容语法: {args_variants}{detail}")


def run_cmd_soft(cmd, timeout=15):
    try:
        subprocess.run(
            cmd,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        pass


def warp_cli_responsive():
    try:
        returncode, output = run_warp_cli("status", timeout=5, quiet=True, check=False)
    except RuntimeError:
        return False
    return returncode == 0 or bool(output)


def wait_for_warp_cli_ready(timeout=WARP_SERVICE_READY_TIMEOUT):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if warp_active(WARP_SERVICE) and warp_cli_responsive():
            return
        time.sleep(1)
    raise RuntimeError(
        f"{WARP_SERVICE} 已启动，但 warp-cli 在 {timeout}s 内未准备就绪；"
        "此时继续切换 mode warp 很容易卡死"
    )


def warp_registration_exists():
    try:
        returncode, out = run_warp_cli("registration show", timeout=8, quiet=True, check=False)
    except RuntimeError:
        return False
    return returncode == 0 and bool(out)


def wait_for_warp_mode(timeout=45, preferred_mode=None):
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = {
            "proxy": warp_proxy_ready(),
            "tun": warp_tunnel_ready(),
        }
        if preferred_mode and status.get(preferred_mode):
            return preferred_mode
        if status["proxy"]:
            return "proxy"
        if status["tun"]:
            return "tun"
        time.sleep(1)
    return None


def configure_warpsvc_tunnel():
    ensure_warp_package()

    ui.step("初始化 Cloudflare WARP 系统隧道模式")
    run_cmd(f"systemctl enable --now {WARP_SERVICE}")
    wait_for_warp_cli_ready()
    run_cmd_soft(warp_cli_cmd("disconnect"), timeout=8)

    if not warp_registration_exists():
        run_compatible_warp_cli("registration new", "register", timeout=WARP_CLI_TIMEOUT)

    run_warp_cli("tunnel protocol set MASQUE", timeout=WARP_CLI_TIMEOUT)
    try:
        run_compatible_warp_cli("mode warp", "set-mode warp", timeout=WARP_CLI_TIMEOUT)
    except RuntimeError as e:
        raise RuntimeError(
            "切换到 Cloudflare WARP 系统隧道模式失败或超时；"
            "这通常意味着 warp-svc 尚未真正 ready，或 VPS 在接管全局链路时卡住"
        ) from e

    try:
        run_warp_cli("connect", timeout=WARP_CONNECT_TIMEOUT)
    except RuntimeError as e:
        raise RuntimeError(
            "Cloudflare WARP connect 失败或超时；"
            "系统隧道模式已开始接管主机链路，但数据面没有在预期时间内就绪"
        ) from e


def singbox_installed():
    result = subprocess.run(
        "which sing-box",
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.returncode == 0


def ensure_warp():
    if warp_proxy_ready():
        ui.success("检测到 WARP 本地代理模式 (127.0.0.1:40000)")
        return "proxy"

    if warp_tunnel_ready():
        ui.success("检测到系统级 WARP 隧道模式")
        return "tun"

    ui.step("安装 WARP")
    configure_warpsvc_tunnel()

    mode = wait_for_warp_mode(preferred_mode="tun")
    if mode == "proxy":
        ui.success("WARP 安装完成，当前使用本地代理模式")
        return "proxy"

    if mode == "tun":
        ui.success("WARP 安装完成，当前使用系统隧道模式")
        return "tun"

    active_services = [svc for svc in (WARP_SERVICE, *LEGACY_WARP_SERVICES) if warp_active(svc)]
    if active_services:
        services = ", ".join(active_services)
        raise RuntimeError(
            f"WARP 服务已运行({services})，但既未提供 127.0.0.1:{WARP_PROXY_PORT} 本地代理，"
            "也未建立系统级 WARP 隧道；请检查 warp-cli 状态与当前模式配置"
        )

    raise RuntimeError("WARP 安装后既未检测到本地代理，也未检测到系统级隧道")


def ensure_singbox():
    if singbox_installed():
        ui.success("sing-box 已存在")
        return

    ui.step("安装 sing-box")
    run_cmd("curl -fsSL -o install.sh https://sing-box.app/install.sh")
    run_cmd("sh install.sh")
    if not singbox_installed():
        raise RuntimeError("sing-box 安装失败")


def ensure_dependencies():
    require_root()
    ensure_ss_tool()
    warp_mode = ensure_warp()
    ensure_singbox()
    ensure_port_safety(warp_mode)
    print_port_snapshot()
    return warp_mode


if __name__ == "__main__":
    ui.banner("依赖自检", "WARP、sing-box 与端口占用检查")
    try:
        ensure_dependencies()
        ui.success("基础依赖检查完成")
    except RuntimeError as e:
        ui.error(str(e))
        raise SystemExit(1)
