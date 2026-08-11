import os
import sys
import re
from . import ui

def parse_wg_config(content: str) -> dict:
    """解析标准 WireGuard 配置内容（字符串，非文件路径）。"""
    # 移除注释和空行
    lines = []
    for line in content.splitlines():
        line = line.split('#')[0].strip()
        if line:
            lines.append(line)

    sections = {}
    current_section = None

    for line in lines:
        if line.startswith('[') and line.endswith(']'):
            current_section = line[1:-1].strip().lower()
            sections.setdefault(current_section, [])
        elif current_section:
            if '=' in line:
                key, val = line.split('=', 1)
                sections[current_section].append((key.strip().lower(), val.strip()))

    interface = dict(sections.get('interface', []))
    peer = dict(sections.get('peer', []))

    private_key = interface.get('privatekey')
    address_raw = interface.get('address')
    dns_raw = interface.get('dns')
    
    peer_public_key = peer.get('publickey')
    preshared_key = peer.get('presharedkey')
    endpoint = peer.get('endpoint')
    allowed_ips_raw = peer.get('allowedips')

    if not private_key:
        raise ValueError("WireGuard 配置缺少 [Interface] 下的 'PrivateKey'")
    if not address_raw:
        raise ValueError("WireGuard 配置缺少 [Interface] 下的 'Address'")
    if not peer_public_key:
        raise ValueError("WireGuard 配置缺少 [Peer] 下的 'PublicKey'")
    if not endpoint:
        raise ValueError("WireGuard 配置缺少 [Peer] 下的 'Endpoint'")

    addresses = [a.strip() for a in address_raw.split(',') if a.strip()]
    dns = [d.strip() for d in dns_raw.split(',') if d.strip()] if dns_raw else []
    allowed_ips = [ip.strip() for ip in allowed_ips_raw.split(',') if ip.strip()] if allowed_ips_raw else ["0.0.0.0/0", "::/0"]

    # 解析 Endpoint
    if ':' not in endpoint:
        raise ValueError(f"无效的 Endpoint: {endpoint}")
    
    if endpoint.startswith('['):
        match = re.match(r'^\[(.*)\]:(\d+)$', endpoint)
        if not match:
            raise ValueError(f"无效的 IPv6 Endpoint: {endpoint}")
        endpoint_host = match.group(1)
        endpoint_port = int(match.group(2))
    else:
        parts = endpoint.rsplit(':', 1)
        if len(parts) != 2:
            raise ValueError(f"无效的 Endpoint 格式: {endpoint}")
        endpoint_host = parts[0]
        endpoint_port = int(parts[1])

    return {
        "private_key": private_key,
        "address": addresses,
        "dns": dns,
        "peer_public_key": peer_public_key,
        "preshared_key": preshared_key,
        "endpoint_host": endpoint_host,
        "endpoint_port": endpoint_port,
        "allowed_ips": allowed_ips,
    }

def read_wg_config_interactive() -> str:
    """交互式读取 WireGuard 配置，支持环境变量。"""
    env_content = os.environ.get("WG_CONFIG")
    if env_content and env_content.strip():
        ui.info("使用环境变量 WG_CONFIG 中的配置")
        return env_content.strip()

    env_file = os.environ.get("WG_CONFIG_FILE")
    if env_file and env_file.strip():
        if os.path.exists(env_file):
            ui.info(f"使用环境变量 WG_CONFIG_FILE 指定的文件: {env_file}")
            with open(env_file, 'r', encoding='utf-8') as f:
                return f.read().strip()
        else:
            ui.warning(f"WG_CONFIG_FILE 路径不存在: {env_file}")

    ui.section("WireGuard 配置")
    print("请粘贴 WireGuard 配置内容 (输入完毕后按 Ctrl+D 结束):", flush=True)

    try:
        content = sys.stdin.read()
    except KeyboardInterrupt:
        print()
        raise RuntimeError("用户取消了交互式输入")

    if not content.strip():
        raise RuntimeError("WireGuard 配置内容不能为空")

    return content.strip()

def build_singbox_wg_outbound(wg_params: dict, tag: str = "warp-out") -> dict:
    """将解析后的参数转换为 sing-box WireGuard outbound。"""
    peer = {
        "public_key": wg_params["peer_public_key"],
        "allowed_ips": wg_params.get("allowed_ips", ["0.0.0.0/0", "::/0"]),
    }
    if wg_params.get("preshared_key"):
        peer["pre_shared_key"] = wg_params["preshared_key"]

    return {
        "type": "wireguard",
        "tag": tag,
        "server": wg_params["endpoint_host"],
        "server_port": wg_params["endpoint_port"],
        "local_address": wg_params["address"],
        "private_key": wg_params["private_key"],
        "peers": [peer],
        "mtu": 1280,
    }
