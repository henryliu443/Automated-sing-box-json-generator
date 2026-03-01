import subprocess
import secrets
import string
import re

def gen_pwd(length=20):
    chars = string.ascii_letters + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))

def generate_credentials():
    T_U = subprocess.check_output("sing-box generate uuid", shell=True, text=True).strip()

    r_raw = subprocess.check_output("sing-box generate reality-keypair", shell=True, text=True)

    m_prv = re.search(r"PrivateKey:\s*(.*)", r_raw)
    m_pub = re.search(r"PublicKey:\s*(.*)", r_raw)

    return {
        "uuid": T_U,
        "private_key": m_prv.group(1),
        "public_key": m_pub.group(1),
        "pwd_anytls": gen_pwd(),
        "pwd_tuic": gen_pwd(),
        "pwd_hy2": gen_pwd(),
        "pwd_obfs": gen_pwd()
    }