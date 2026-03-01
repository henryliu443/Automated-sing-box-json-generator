import os
import shlex
import subprocess

from config import HY2_CERT_PATH, HY2_KEY_PATH, TUIC_CERT_PATH, TUIC_KEY_PATH
from installer import ensure_ss_tool, get_port_owners, nginx_active, run_cmd

ACME_SH_PATH = "/root/.acme.sh/acme.sh"
ACME_INSTALL_URL = "https://get.acme.sh"
ACME_CA = "letsencrypt"
CERT_VALIDITY_WINDOW = 30 * 24 * 3600
ACME_WEBROOT = "/var/www/html"
CF_TOKEN_ENV = "CF_Token"
CF_ZONE_ID_ENV = "CF_Zone_ID"


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


def _tcp_port_owners(port):
    ensure_ss_tool()
    return get_port_owners(port, "tcp")


def _nginx_listening_80():
    owners, _ = _tcp_port_owners(80)
    return "nginx" in owners


def _has_cloudflare_dns_credentials():
    return bool(os.environ.get(CF_TOKEN_ENV) and os.environ.get(CF_ZONE_ID_ENV))


def _choose_challenge_mode():
    if _has_cloudflare_dns_credentials():
        return "dns_cf"

    if os.path.isdir(ACME_WEBROOT) and _nginx_listening_80():
        return "webroot"

    return "standalone"


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

    print("安装 openssl (证书校验依赖)...")
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


def _ensure_socat():
    if _command_exists("socat"):
        return

    print("安装 socat (ACME standalone 依赖)...")
    if _command_exists("apt-get"):
        run_cmd("DEBIAN_FRONTEND=noninteractive apt-get update")
        run_cmd("DEBIAN_FRONTEND=noninteractive apt-get install -y socat")
        return
    if _command_exists("dnf"):
        run_cmd("dnf install -y socat")
        return
    if _command_exists("yum"):
        run_cmd("yum install -y socat")
        return

    raise RuntimeError("未检测到可用包管理器，无法自动安装 socat")


def _ensure_webroot_ready():
    if not os.path.isdir(ACME_WEBROOT):
        raise RuntimeError(
            f"检测到 webroot 模式但目录不存在: {ACME_WEBROOT}；"
            "请先部署并配置 nginx 站点根目录"
        )
    if not nginx_active():
        raise RuntimeError("检测到 webroot 模式但 nginx 未处于 active 状态")

    owners, raw = _tcp_port_owners(80)
    if "nginx" not in owners:
        raise RuntimeError(
            "检测到 webroot 模式但 nginx 未监听 80 端口；"
            f"当前监听者: {sorted(owners)}\n监听明细:\n{raw or '(empty)'}"
        )


def _verify_webroot_probe():
    token = "singbox-acme-probe"
    challenge_dir = os.path.join(ACME_WEBROOT, ".well-known", "acme-challenge")
    probe_file = os.path.join(challenge_dir, token)
    os.makedirs(challenge_dir, exist_ok=True)

    with open(probe_file, "w", encoding="utf-8") as f:
        f.write(token)

    try:
        out = run_cmd(f"curl -fsS --max-time 5 http://127.0.0.1/.well-known/acme-challenge/{token}")
        if token not in out:
            raise RuntimeError("nginx 已监听 80，但 ACME challenge 路径未正确映射到 webroot")
    finally:
        try:
            os.remove(probe_file)
        except FileNotFoundError:
            pass


def _resolve_acme_sh():
    if os.path.isfile(ACME_SH_PATH):
        return ACME_SH_PATH
    if _command_exists("acme.sh"):
        return "acme.sh"

    print("安装 acme.sh...")
    run_cmd(f"curl -fsSL {ACME_INSTALL_URL} | sh")

    if os.path.isfile(ACME_SH_PATH):
        return ACME_SH_PATH
    if _command_exists("acme.sh"):
        return "acme.sh"
    raise RuntimeError("acme.sh 安装失败")


def _issue_and_install_cert(acme_sh, host, cert_path, key_path, challenge_mode):
    os.makedirs(os.path.dirname(cert_path), exist_ok=True)
    os.makedirs(os.path.dirname(key_path), exist_ok=True)

    if _cert_is_valid_for_host(cert_path, host):
        print(f"证书已可用且域名匹配，跳过重签: {host}")
        return

    print(f"签发/更新证书: {host}")
    run_cmd(f"{_q(acme_sh)} --set-default-ca --server {ACME_CA}")

    if challenge_mode == "dns_cf":
        cf_token = os.environ.get(CF_TOKEN_ENV, "")
        cf_zone_id = os.environ.get(CF_ZONE_ID_ENV, "")
        run_cmd(
            f"{CF_TOKEN_ENV}={_q(cf_token)} {CF_ZONE_ID_ENV}={_q(cf_zone_id)} "
            f"{_q(acme_sh)} --issue --dns dns_cf -d {_q(host)} --keylength ec-256 --server {ACME_CA}"
        )
    elif challenge_mode == "webroot":
        run_cmd(
            f"{_q(acme_sh)} --issue --webroot {_q(ACME_WEBROOT)} "
            f"-d {_q(host)} --keylength ec-256 --server {ACME_CA}"
        )
    else:
        run_cmd(
            f"{_q(acme_sh)} --issue --standalone -d {_q(host)} --keylength ec-256 --server {ACME_CA}"
        )

    run_cmd(
        f"{_q(acme_sh)} --install-cert -d {_q(host)} --ecc "
        f"--fullchain-file {_q(cert_path)} "
        f"--key-file {_q(key_path)} "
        "--reloadcmd 'systemctl restart sing-box'"
    )
    run_cmd(f"chmod 600 {_q(key_path)}")


def ensure_tls_certificates(protocol_hosts):
    for key in ("tuic", "hy2"):
        if key not in protocol_hosts:
            raise RuntimeError(f"protocol_hosts 缺少 {key} 域名")

    _ensure_openssl()
    challenge_mode = _choose_challenge_mode()
    if challenge_mode == "dns_cf":
        print("证书挑战方式: Cloudflare DNS-01 (dns_cf)")
    elif challenge_mode == "webroot":
        print(f"证书挑战方式: HTTP-01 webroot ({ACME_WEBROOT})")
        _ensure_webroot_ready()
        _verify_webroot_probe()
    else:
        owners, raw = _tcp_port_owners(80)
        if owners:
            raise RuntimeError(
                "80 端口已被占用且无法使用 standalone；"
                f"当前监听者: {sorted(owners)}\n监听明细:\n{raw or '(empty)'}\n"
                "请改用 Cloudflare DNS-01 或先配置 nginx + webroot"
            )
        print("证书挑战方式: HTTP-01 standalone (临时占用 80 端口)")
        _ensure_socat()

    acme_sh = _resolve_acme_sh()

    _issue_and_install_cert(
        acme_sh=acme_sh,
        host=protocol_hosts["tuic"],
        cert_path=TUIC_CERT_PATH,
        key_path=TUIC_KEY_PATH,
        challenge_mode=challenge_mode,
    )
    _issue_and_install_cert(
        acme_sh=acme_sh,
        host=protocol_hosts["hy2"],
        cert_path=HY2_CERT_PATH,
        key_path=HY2_KEY_PATH,
        challenge_mode=challenge_mode,
    )
