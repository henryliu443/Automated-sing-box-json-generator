import importlib
import time
import urllib.request
from urllib.error import URLError

BASE_URL = "https://raw.githubusercontent.com/henryliu443/Automated-sing-box-json-generator/refs/heads/main"
REQUIRED_FILES = [
    "deploy.py",
    "config.py",
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
        print(f"[bootstrap] refreshing {name} ...")
        try:
            download_file(name)
        except (URLError, TimeoutError) as e:
            raise RuntimeError(f"bootstrap download failed: {name}: {e}") from e


if __name__ == "__main__":
    refresh_required_files()
    deploy = importlib.import_module("deploy")
    raise SystemExit(deploy.main())
