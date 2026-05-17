import json
import sys
from urllib.parse import urlencode

from . import ui
from .config import (
    PROTOCOL_DEFS,
    build_client_config,
    get_reality_decoy_server,
)
from .qr_payload import (
    COMPRESSED_JSON_MODE,
    MULTIPART_JSON_MODE,
    RAW_JSON_MODE,
    decode_qr_json_tokens,
    make_qr_json_payload_plan,
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


def export_qr():
    data = _require_state()
    opts = data.get("anti_detection")
    creds = data["credentials"]
    hosts = data["protocol_hosts"]
    protocols = data["enabled_protocols"]

    try:
        import qrcode
    except ImportError:
        ui.error("需要安装 qrcode 库: pip3 install qrcode")
        export_links()
        return

    for proto in protocols:
        builder = _LINK_BUILDERS.get(proto)
        if not builder:
            continue
        link = builder(creds, hosts, opts)
        ui.section(f"{proto} 分享二维码")
        qr = _new_qr(qrcode)
        qr.add_data(link)
        qr.make(fit=True)
        qr.print_ascii(out=sys.stdout, invert=True)
        print(link)


def _build_client_config_from_state(data, compact=False):
    return build_client_config(
        data["credentials"],
        protocol_hosts=data["protocol_hosts"],
        enabled_protocols=data["enabled_protocols"],
        server_ip=data.get("server_ip"),
        fingerprint_opts=data.get("anti_detection"),
        compact=compact,
    )


def _new_qr(qrcode):
    return qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=1,
        border=1,
    )


def _qr_fits(qrcode, text):
    try:
        qr = _new_qr(qrcode)
        qr.add_data(text)
        qr.make(fit=True)
        return True
    except (qrcode.exceptions.DataOverflowError, ValueError):
        return False


def _print_qr(qrcode, text):
    qr = _new_qr(qrcode)
    qr.add_data(text)
    qr.make(fit=True)
    qr.print_ascii(out=sys.stdout, invert=True)


def export_qr_json():
    data = _require_state()

    try:
        import qrcode
    except ImportError:
        ui.error("需要安装 qrcode 库: pip3 install qrcode")
        return

    client_cfg = _build_client_config_from_state(data, compact=False)
    try:
        plan = make_qr_json_payload_plan(client_cfg, lambda token: _qr_fits(qrcode, token))
    except ValueError as e:
        raise RuntimeError(f"无法生成可恢复的 JSON 二维码: {e}") from e

    if plan.mode == RAW_JSON_MODE:
        ui.section("全量 JSON 配置二维码")
        _print_qr(qrcode, plan.tokens[0])
        ui.success(f"已生成原始 JSON 二维码，可直接导入客户端 ({plan.original_chars} 字符)")
        return

    if plan.mode == COMPRESSED_JSON_MODE:
        ui.section("压缩 JSON 配置二维码")
        _print_qr(qrcode, plan.tokens[0])
        ui.info("扫描内容为 SBOX:ZLIB45 压缩载荷，使用 decode-qr-json 还原完整 JSON。")
        ui.command("automated-sing-box-generator decode-qr-json --input scans.txt --output client.json")
        ui.kv("original_chars", plan.original_chars)
        ui.kv("compressed_bytes", plan.compressed_bytes)
        ui.kv("payload_sha256", plan.sha256)
        return

    if plan.mode == MULTIPART_JSON_MODE:
        ui.section(f"压缩 JSON 分片二维码 ({len(plan.tokens)} 张)")
        ui.info("请扫描全部分片，每行保存一个扫描结果；分片顺序不限，解码时会校验完整性。")
        ui.command("automated-sing-box-generator decode-qr-json --input scans.txt --output client.json")
        ui.kv("original_chars", plan.original_chars)
        ui.kv("compressed_bytes", plan.compressed_bytes)
        ui.kv("payload_sha256", plan.sha256)
        for index, token in enumerate(plan.tokens, 1):
            ui.section(f"分片 {index}/{len(plan.tokens)}")
            _print_qr(qrcode, token)
        return

    raise RuntimeError(f"未知 QR JSON 输出模式: {plan.mode}")


def _read_qr_token_lines(input_path=None, tokens=None):
    result = []

    if input_path:
        if input_path == "-":
            result.extend(sys.stdin.read().splitlines())
        else:
            with open(input_path, "r", encoding="utf-8") as f:
                result.extend(f.read().splitlines())

    if tokens:
        result.extend(tokens)

    if not result and not sys.stdin.isatty():
        result.extend(sys.stdin.read().splitlines())

    return [line for line in result if line != ""]


def decode_qr_json(input_path=None, output=None, tokens=None):
    token_lines = _read_qr_token_lines(input_path=input_path, tokens=tokens)
    try:
        compact_text = decode_qr_json_tokens(token_lines)
        payload = json.loads(compact_text)
    except (ValueError, json.JSONDecodeError) as e:
        raise RuntimeError(f"无法解码 QR JSON: {e}") from e

    text = json.dumps(payload, indent=2, ensure_ascii=False)
    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        ui.success(f"客户端配置已写入: {output}")
    else:
        print(text)


def export_client_config(fmt="json", output=None):
    if fmt == "json":
        export_json(output)
    elif fmt == "link":
        export_links()
    elif fmt == "qr":
        export_qr()
    elif fmt == "qr-json":
        export_qr_json()
    else:
        raise RuntimeError(f"不支持的导出格式: {fmt}")
