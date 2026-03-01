import importlib
import os
import urllib.request

BASE_URL = "https://raw.githubusercontent.com/henryliu443/Automated-sing-box-json-generator/refs/heads/main"
REQUIRED_FILES = [
    "deploy.py",
    "config.py",
    "installer.py",
    "credentials.py",
    "watchdog.py",
]


def ensure_required_files():
    for name in REQUIRED_FILES:
        if os.path.exists(name):
            continue
        url = f"{BASE_URL}/{name}"
        print(f"[bootstrap] downloading {name} ...")
        urllib.request.urlretrieve(url, name)


if __name__ == "__main__":
    ensure_required_files()
    deploy = importlib.import_module("deploy")
    raise SystemExit(deploy.main())
