import json
import sys
from urllib.parse import urlencode

from . import ui
from .config import (
    PROTOCOL_DEFS,
    build_client_config,
    get_reality_decoy_server,
)
from .state import load_state


def _require_state():
    data = load_state()
    if not data:
        raise RuntimeError("未找到部署状态，请先运行 deploy")
    for key in ("credentials", "protocol_hosts", "enabled_protocols"):
        if key not in data:
            raise RuntimeError(f"部署状态缺少 {key}，请重新运行 deploy")
    return data


def build_tuic_link(creds, hosts, opts=None):
    host = hosts["tuic"]
    port = PROTOCOL_DEFS["tuic"]["server_port"]
    params = urlencode({
        "congestion_control": "bbr",
        "udp_relay_mode": "quic",
        "sni": host,
    })
    return f"tuic://{creds['uuid']}:{creds['pwd_tuic']}@{host}:{port}?{params}#TUIC"


def build_hy2_link(creds, hosts, opts=None):
    host = hosts["hy2"]
    port = PROTOCOL_DEFS["hy2"]["server_port"]
    params = urlencode({
        "obfs": "salamander",
        "obfs-password": creds["pwd_obfs"],
        "sni": host,
    })
    return f"hy2://{creds['pwd_hy2']}@{host}:{port}?{params}#Hysteria2"


def build_anytls_link(creds, hosts, opts=None):
    host = hosts["reality"]
    port = PROTOCOL_DEFS["anytls"]["server_port"]
    params = urlencode({
        "security": "reality",
        "sni": get_reality_decoy_server(opts),
        "fp": "chrome",
        "pbk": creds["public_key"],
        "sid": creds["short_id"],
    })
    return f"anytls://{creds['pwd_anytls']}@{host}:{port}?{params}#AnyTLS"


_LINK_BUILDERS = {
    "tuic": build_tuic_link,
    "hy2": build_hy2_link,
    "anytls": build_anytls_link,
}


def export_json(output=None):
    data = _require_state()
    client_cfg = _build_client_config_from_state(data)
    text = json.dumps(client_cfg, indent=2, ensure_ascii=False)

    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        ui.success(f"客户端配置已写入: {output}")
    else:
        print(text)


def export_links():
    data = _require_state()
    opts = data.get("anti_detection")
    creds = data["credentials"]
    hosts = data["protocol_hosts"]
    protocols = data["enabled_protocols"]

    for proto in protocols:
        builder = _LINK_BUILDERS.get(proto)
        if builder:
            link = builder(creds, hosts, opts)
            ui.kv(proto, link)


def _build_client_config_from_state(data):
    return build_client_config(
        data["credentials"],
        protocol_hosts=data["protocol_hosts"],
        enabled_protocols=data["enabled_protocols"],
        server_ip=data.get("server_ip"),
        fingerprint_opts=data.get("anti_detection"),
    )


def export_client_config(fmt="json", output=None):
    if fmt == "json":
        export_json(output)
    elif fmt == "link":
        export_links()
    else:
        raise RuntimeError(f"不支持的导出格式: {fmt}")
