import subprocess
import time
import select


def run_cmd(cmd, timeout=1800):
    print(f"[RUN] {cmd}")
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
        # Always print a live heartbeat so long-running installers never look frozen.
        if now - last_log >= 1:
            print(
                f"\r[WAIT] {spinner[spin_idx % len(spinner)]} command running... {elapsed}s",
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


def require_root():
    uid = subprocess.run("id -u", shell=True, stdout=subprocess.PIPE, text=True, check=True).stdout.strip()
    if uid != "0":
        raise RuntimeError("请使用 root 运行")


def warp_active():
    result = subprocess.run(
        "systemctl is-active warp-go",
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
    # Prefer functional check: if local SOCKS5 WARP proxy works, no install needed.
    if warp_proxy_ready():
        print("WARP 代理已就绪，跳过安装")
        return

    # Fallback compatibility check for users who manage warp-go via systemd.
    if warp_active():
        print("warp-go 服务已运行")
        return

    print("安装 WARP...")
    run_cmd("wget -O warp-go.sh https://gitlab.com/fscarmen/warp/-/raw/main/warp-go.sh")
    run_cmd("bash warp-go.sh 4")

    out = run_cmd("curl -s https://www.cloudflare.com/cdn-cgi/trace")
    if "warp=on" not in out and "warp=plus" not in out:
        raise RuntimeError("WARP 验证失败")


def ensure_singbox():
    if singbox_installed():
        print("sing-box 已存在")
        return

    print("安装 sing-box...")
    run_cmd("curl -fsSL -o install.sh https://sing-box.app/install.sh")
    run_cmd("sh install.sh")
    if not singbox_installed():
        raise RuntimeError("sing-box 安装失败")


def ensure_dependencies():
    require_root()
    ensure_warp()
    ensure_singbox()


if __name__ == "__main__":
    print("=== One-Click Deploy ===")
    try:
        ensure_dependencies()
        print("基础依赖检查完成")
    except RuntimeError as e:
        print(str(e))
        raise SystemExit(1)
