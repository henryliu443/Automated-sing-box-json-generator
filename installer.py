import re
import select
import subprocess
import time

import cli_ui as ui


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


def ensure_port_safety():
    ensure_ss_tool()

    # sing-box inbound ports
    assert_port_allowed(23244, "tcp", {"sing-box"})
    assert_port_allowed(7443, "udp", {"sing-box"})
    assert_port_allowed(9443, "udp", {"sing-box"})

    # local WARP socks proxy
    assert_port_allowed(40000, "tcp", {"warp-svc", "warp-go"})
    assert_port_required(40000, "tcp", {"warp-svc", "warp-go"})


def warp_active(service):
    result = subprocess.run(
        f"systemctl is-active {service}",
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip() == "active"


def warp_proxy_ready():
    cmd = (
        'curl -s --proxy "socks5h://127.0.0.1:40000" --max-time 6 '
        "https://www.cloudflare.com/cdn-cgi/trace"
    )
    result = subprocess.run(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    out = result.stdout
    return result.returncode == 0 and ("warp=on" in out or "warp=plus" in out)


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
        ui.success("WARP 代理已就绪，跳过安装")
        return

    active_services = [svc for svc in ("warp-go", "warp-svc") if warp_active(svc)]
    if active_services:
        services = ", ".join(active_services)
        raise RuntimeError(
            f"WARP 服务已运行({services})，但 127.0.0.1:40000 代理不可用；"
            "请先开启 WARP 本地代理后再重试"
        )

    ui.step("安装 WARP")
    run_cmd("wget -O warp-go.sh https://gitlab.com/fscarmen/warp/-/raw/main/warp-go.sh")
    run_cmd("bash warp-go.sh 4")

    if not warp_proxy_ready():
        raise RuntimeError("WARP 安装后代理仍不可用(127.0.0.1:40000)")


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
    ensure_warp()
    ensure_singbox()
    ensure_port_safety()
    print_port_snapshot()


if __name__ == "__main__":
    ui.banner("依赖自检", "WARP、sing-box 与端口占用检查")
    try:
        ensure_dependencies()
        ui.success("基础依赖检查完成")
    except RuntimeError as e:
        ui.error(str(e))
        raise SystemExit(1)
