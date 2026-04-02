import os
import shlex
import subprocess

import cli_ui as ui
from config import HY2_CERT_PATH, HY2_KEY_PATH, TUIC_CERT_PATH, TUIC_KEY_PATH
from installer import SINGBOX_SERVICE, run_cmd

ACME_SH_PATH = "/root/.acme.sh/acme.sh"
ACME_INSTALL_URL = "https://get.acme.sh"
ACME_CA = "letsencrypt"
CERT_VALIDITY_WINDOW = 30 * 24 * 3600
CF_TOKEN_ENV = "CF_Token"
CF_ZONE_ID_ENV = "CF_Zone_ID"
ACME_RELOAD_CMD = f"systemctl try-restart {SINGBOX_SERVICE} >/dev/null 2>&1 || true"


def _q(value):
    return shlex.quote(value)


def _command_exists(cmd):
    result = subprocess.run(
        f"command -v {_q(cmd)} >/dev/null 2>&1",
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    return result.returncode == 0


def _ensure_dns_credentials(cf_token=None, cf_zone_id=None):
    token = (cf_token or os.environ.get(CF_TOKEN_ENV, "")).strip()
    zone_id = (cf_zone_id or os.environ.get(CF_ZONE_ID_ENV, "")).strip()
    if token and zone_id:
        return token, zone_id
    raise RuntimeError(
        "未检测到 Cloudflare DNS-01 凭据；请先设置环境变量:\n"
        "export CF_Token=\"...\"\n"
        "export CF_Zone_ID=\"...\""
    )


def _cert_is_valid_for_host(cert_path, host):
    if not os.path.isfile(cert_path):
        return False

    try:
        not_expiring = subprocess.run(
            [
                "openssl",
                "x509",
                "-in",
                cert_path,
                "-noout",
                "-checkend",
                str(CERT_VALIDITY_WINDOW),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        ).returncode == 0
    except FileNotFoundError:
        return False
    if not not_expiring:
        return False

    try:
        san_ext = subprocess.check_output(
            ["openssl", "x509", "-in", cert_path, "-noout", "-ext", "subjectAltName"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

    return f"DNS:{host}" in san_ext


def _ensure_openssl():
    if _command_exists("openssl"):
        return

    ui.step("安装 openssl (证书校验依赖)")
    if _command_exists("apt-get"):
        run_cmd("DEBIAN_FRONTEND=noninteractive apt-get update")
        run_cmd("DEBIAN_FRONTEND=noninteractive apt-get install -y openssl")
        return
    if _command_exists("dnf"):
        run_cmd("dnf install -y openssl")
        return
    if _command_exists("yum"):
        run_cmd("yum install -y openssl")
        return

    raise RuntimeError("未检测到可用包管理器，无法自动安装 openssl")


def _resolve_acme_sh():
    if os.path.isfile(ACME_SH_PATH):
        return ACME_SH_PATH
    if _command_exists("acme.sh"):
        return "acme.sh"

    ui.step("安装 acme.sh")
    run_cmd(f"curl -fsSL {ACME_INSTALL_URL} | sh")

    if os.path.isfile(ACME_SH_PATH):
        return ACME_SH_PATH
    if _command_exists("acme.sh"):
        return "acme.sh"
    raise RuntimeError("acme.sh 安装失败")


def _acme_issue_skipped_not_due(output: str) -> bool:
    """acme.sh 在证书未到期时会跳过 --issue 并以非零退出；此时应继续 --install-cert。"""
    text = (output or "").lower()
    if "domains not changed" in text and "skipping" in text:
        return True
    if "next renewal time" in text and "skipping" in text:
        return True
    return False


def _run_acme_issue(acme_sh, host, cf_token, cf_zone_id) -> None:
    cmd = (
        f"{CF_TOKEN_ENV}={_q(cf_token)} {CF_ZONE_ID_ENV}={_q(cf_zone_id)} "
        f"{_q(acme_sh)} --issue --dns dns_cf -d {_q(host)} --keylength ec-256 --server {ACME_CA}"
    )
    ui.command(cmd)
    result = subprocess.run(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    out = (result.stdout or "").strip()
    if out:
        print(out, flush=True)
    if result.returncode == 0:
        return
    if _acme_issue_skipped_not_due(out):
        ui.info("acme.sh 已跳过签发（未到期或域名未变），继续安装证书到目标路径")
        return
    raise RuntimeError(f"acme.sh --issue 失败 (exit {result.returncode}):\n{out}")


def _issue_and_install_cert(acme_sh, host, cert_path, key_path, cf_token, cf_zone_id):
    os.makedirs(os.path.dirname(cert_path), exist_ok=True)
    os.makedirs(os.path.dirname(key_path), exist_ok=True)

    if _cert_is_valid_for_host(cert_path, host):
        ui.success(f"证书已可用且域名匹配，跳过重签: {host}")
        return

    ui.step(f"签发/更新证书 (Cloudflare DNS-01): {host}")
    run_cmd(f"{_q(acme_sh)} --set-default-ca --server {ACME_CA}")
    _run_acme_issue(acme_sh, host, cf_token, cf_zone_id)
    run_cmd(
        f"{_q(acme_sh)} --install-cert -d {_q(host)} --ecc "
        f"--fullchain-file {_q(cert_path)} "
        f"--key-file {_q(key_path)} "
        f"--reloadcmd {_q(ACME_RELOAD_CMD)}"
    )
    run_cmd(f"chmod 600 {_q(key_path)}")


def ensure_tls_certificates(protocol_hosts, cf_token=None, cf_zone_id=None):
    for key in ("tuic", "hy2"):
        if key not in protocol_hosts:
            raise RuntimeError(f"protocol_hosts 缺少 {key} 域名")

    _ensure_openssl()
    cf_token, cf_zone_id = _ensure_dns_credentials(cf_token=cf_token, cf_zone_id=cf_zone_id)
    ui.info("证书挑战方式: Cloudflare DNS-01 (dns_cf)")
    acme_sh = _resolve_acme_sh()

    _issue_and_install_cert(
        acme_sh=acme_sh,
        host=protocol_hosts["tuic"],
        cert_path=TUIC_CERT_PATH,
        key_path=TUIC_KEY_PATH,
        cf_token=cf_token,
        cf_zone_id=cf_zone_id,
    )
    _issue_and_install_cert(
        acme_sh=acme_sh,
        host=protocol_hosts["hy2"],
        cert_path=HY2_CERT_PATH,
        key_path=HY2_KEY_PATH,
        cf_token=cf_token,
        cf_zone_id=cf_zone_id,
    )
