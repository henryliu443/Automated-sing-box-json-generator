import os
import sys
import re
from . import ui

def parse_wg_config(content: str) -> dict:
    """解析标准 WireGuard 配置内容（支持单/多 Peer，不使用上传文件）。"""
    # 移除注释和空行
    lines = []
    for line in content.splitlines():
        line = line.split('#')[0].strip()
        if line:
            lines.append(line)

    interface = {}
    peers = []
    
    current_section = None
    current_peer = {}

    for line in lines:
        if line.startswith('[') and line.endswith(']'):
            section_name = line[1:-1].strip().lower()
            if section_name == 'peer':
                if current_peer:
                    peers.append(current_peer)
                current_peer = {}
            current_section = section_name
        elif current_section:
            if '=' in line:
                key, val = line.split('=', 1)
                key = key.strip().lower()
                val = val.strip()
                if current_section == 'interface':
                    interface[key] = val
                elif current_section == 'peer':
                    current_peer[key] = val

    if current_peer:
        peers.append(current_peer)

    private_key = interface.get('privatekey')
    address_raw = interface.get('address')
    dns_raw = interface.get('dns')

    if not private_key:
        raise ValueError("WireGuard 配置缺少 [Interface] 下的 'PrivateKey'")
    if not address_raw:
        raise ValueError("WireGuard 配置缺少 [Interface] 下的 'Address'")
    if not peers:
        raise ValueError("WireGuard 配置缺少 [Peer] 部分")

    addresses = [a.strip() for a in address_raw.split(',') if a.strip()]
    dns = [d.strip() for d in dns_raw.split(',') if d.strip()] if dns_raw else []

    parsed_peers = []
    for p in peers:
        pubkey = p.get('publickey')
        if not pubkey:
            raise ValueError("WireGuard 配置的 [Peer] 缺少 'PublicKey'")
        
        endpoint = p.get('endpoint')
        if not endpoint:
            raise ValueError("WireGuard 配置的 [Peer] 缺少 'Endpoint'")
            
        preshared = p.get('presharedkey')
        allowed_raw = p.get('allowedips')
        allowed = [ip.strip() for ip in allowed_raw.split(',') if ip.strip()] if allowed_raw else ["0.0.0.0/0", "::/0"]
        
        # 解析 Endpoint
        if ':' not in endpoint:
            raise ValueError(f"无效的 Endpoint: {endpoint}")
        if endpoint.startswith('['):
            match = re.match(r'^\[(.*)\]:(\d+)$', endpoint)
            if not match:
                raise ValueError(f"无效的 IPv6 Endpoint: {endpoint}")
            host = match.group(1)
            port = int(match.group(2))
        else:
            parts = endpoint.rsplit(':', 1)
            if len(parts) != 2:
                raise ValueError(f"无效的 Endpoint 格式: {endpoint}")
            host = parts[0]
            port = int(parts[1])
            
        parsed_peers.append({
            "public_key": pubkey,
            "pre_shared_key": preshared,
            "endpoint_host": host,
            "endpoint_port": port,
            "allowed_ips": allowed,
        })

    first_peer = parsed_peers[0]
    
    if len(parsed_peers) > 1:
        ui.warning(f"检测到多个 [Peer] 配置 (共 {len(parsed_peers)} 个)，本工具将生成多 Peer 出站")

    return {
        "private_key": private_key,
        "address": addresses,
        "dns": dns,
        # Flat 格式保持向后兼容（使用第一个 peer）
        "peer_public_key": first_peer["public_key"],
        "preshared_key": first_peer["pre_shared_key"],
        "endpoint_host": first_peer["endpoint_host"],
        "endpoint_port": first_peer["endpoint_port"],
        "allowed_ips": first_peer["allowed_ips"],
        # 新增的多 peer 列表
        "peers": parsed_peers,
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

def build_singbox_wg_outbound(wg_params: dict, tag: str = "warp-out", allow_ipv6: bool = True, mtu: int = 1280) -> dict:
    """将解析后的参数转换为 sing-box WireGuard outbound。"""
    # 优先使用新的 peers 列表
    raw_peers = wg_params.get("peers")
    peers = []
    
    if raw_peers:
        for p in raw_peers:
            peer_allowed = p.get("allowed_ips", ["0.0.0.0/0", "::/0"])
            if not allow_ipv6:
                peer_allowed = [ip for ip in peer_allowed if ":" not in ip]
            
            peer_item = {
                "public_key": p["public_key"],
                "allowed_ips": peer_allowed,
            }
            if p.get("pre_shared_key"):
                peer_item["pre_shared_key"] = p["pre_shared_key"]
            peers.append(peer_item)
            
        first_peer = raw_peers[0]
        server_host = first_peer["endpoint_host"]
        server_port = first_peer["endpoint_port"]
    else:
        # 向后兼容 flat 格式
        peer_allowed = wg_params.get("allowed_ips", ["0.0.0.0/0", "::/0"])
        if not allow_ipv6:
            peer_allowed = [ip for ip in peer_allowed if ":" not in ip]
            
        peer_item = {
            "public_key": wg_params["peer_public_key"],
            "allowed_ips": peer_allowed,
        }
        if wg_params.get("preshared_key"):
            peer_item["pre_shared_key"] = wg_params["preshared_key"]
        peers = [peer_item]
        
        server_host = wg_params["endpoint_host"]
        server_port = wg_params["endpoint_port"]

    env_mtu = os.environ.get("WG_MTU")
    final_mtu = int(env_mtu) if env_mtu else mtu

    return {
        "type": "wireguard",
        "tag": tag,
        "server": server_host,
        "server_port": server_port,
        "local_address": wg_params["address"],
        "private_key": wg_params["private_key"],
        "peers": peers,
        "mtu": final_mtu,
    }
