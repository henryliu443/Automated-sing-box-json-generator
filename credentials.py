import subprocess
import secrets
import string
import re


def gen_pwd(length=20):
    chars = string.ascii_letters + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))


def gen_short_id(length=16):
    return secrets.token_hex(length // 2)


def gen_subdomain_prefix(length=8):
    return secrets.token_hex(length // 2)


def gen_subdomain_prefixes():
    seen = set()
    prefixes = {}
    for key in ("reality", "hy2", "tuic"):
        while True:
            p = gen_subdomain_prefix()
            if p not in seen:
                seen.add(p)
                prefixes[key] = p
                break
    return prefixes


def generate_credentials():
    t_u = subprocess.check_output("sing-box generate uuid", shell=True, text=True).strip()
    r_raw = subprocess.check_output("sing-box generate reality-keypair", shell=True, text=True)

    m_prv = re.search(r"PrivateKey:\s*(.*)", r_raw)
    m_pub = re.search(r"PublicKey:\s*(.*)", r_raw)
    if not t_u or not m_prv or not m_pub:
        raise RuntimeError("生成凭据失败，请确认 sing-box 可用")

    return {
        "uuid": t_u,
        "private_key": m_prv.group(1),
        "public_key": m_pub.group(1),
        "short_id": gen_short_id(),
        "pwd_anytls": gen_pwd(),
        "pwd_tuic": gen_pwd(),
        "pwd_hy2": gen_pwd(),
        "pwd_obfs": gen_pwd(),
    }
