import subprocess


def run_cmd(cmd):
    result = subprocess.run(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"command failed: {cmd}")
    return result.stdout.strip()


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
    if warp_active():
        print("WARP 已运行")
        return

    print("安装 WARP...")
    run_cmd("wget -q -O warp-go.sh https://gitlab.com/fscarmen/warp/-/raw/main/warp-go.sh")
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
