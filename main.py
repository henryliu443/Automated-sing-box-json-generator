import importlib
import os
import time
import urllib.request
from urllib.error import URLError

try:
    import cli_ui as ui
except ModuleNotFoundError:
    class _FallbackUI:
        @staticmethod
        def banner(title, subtitle=None):
            print(f"=== {title} ===")
            if subtitle:
                print(subtitle)

        @staticmethod
        def step(message):
            print(f"[STEP] {message}")

        @staticmethod
        def info(message):
            print(f"[INFO] {message}")

        @staticmethod
        def error(message):
            print(f"[ERR ] {message}")

        @staticmethod
        def success(message):
            print(f"[ OK ] {message}")

    ui = _FallbackUI()

BASE_URL = "https://raw.githubusercontent.com/henryliu443/Automated-sing-box-json-generator/refs/heads/main"
REQUIRED_FILES = [
    "deploy.py",
    "cli_ui.py",
    "config.py",
    "certs.py",
    "installer.py",
    "credentials.py",
    "watchdog.py",
]


def download_file(name):
    url = f"{BASE_URL}/{name}?ts={int(time.time())}"
    with urllib.request.urlopen(url, timeout=20) as resp:
        content = resp.read()
    with open(name, "wb") as f:
        f.write(content)


def refresh_required_files():
    for name in REQUIRED_FILES:
        ui.step(f"刷新远程文件: {name}")
        try:
            download_file(name)
        except (URLError, TimeoutError) as e:
            raise RuntimeError(f"bootstrap download failed: {name}: {e}") from e


def should_refresh_from_remote():
    # If running inside a cloned repository, keep local files and skip bootstrap overwrite.
    return not os.path.isdir(".git")


if __name__ == "__main__":
    if should_refresh_from_remote():
        ui.banner("Bootstrap", "从远程刷新部署脚本")
        refresh_required_files()
    else:
        ui.info("检测到本地仓库，跳过远程刷新")
    deploy = importlib.import_module("deploy")
    raise SystemExit(deploy.main())
