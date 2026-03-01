import subprocess
import sys
import re

print("=== One-Click Deploy ===")

def run_cmd(cmd):
    print(f"[RUN] {cmd}")
    result = subprocess.run(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    if result.returncode != 0:
        print(result.stderr)
        sys.exit(1)
    return result.stdout.strip()

def warp_active():
    result = subprocess.run(
        "systemctl is-active warp-go",
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    return result.stdout.strip() == "active"

def singbox_installed():
    result = subprocess.run(
        "which sing-box",
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    return result.returncode == 0

# root 检查
if subprocess.run("id -u", shell=True, stdout=subprocess.PIPE, text=True).stdout.strip() != "0":
    print("请使用 root 运行")
    sys.exit(1)

# WARP
if not warp_active():
    run_cmd("wget -q -O warp-go.sh https://gitlab.com/fscarmen/warp/-/raw/main/warp-go.sh")
    run_cmd("bash warp-go.sh 4")

    out = run_cmd("curl -s https://www.cloudflare.com/cdn-cgi/trace")
    if not re.search(r"warp=(on|plus)", out):
        print("WARP 验证失败")
        sys.exit(1)
else:
    print("WARP 已运行")

# sing-box
if not singbox_installed():
    run_cmd("curl -fsSL -o install.sh https://sing-box.app/install.sh")
    run_cmd("sh install.sh")

    if not singbox_installed():
        print("sing-box 安装失败")
        sys.exit(1)
else:
    print("sing-box 已存在")

print("部署完成")