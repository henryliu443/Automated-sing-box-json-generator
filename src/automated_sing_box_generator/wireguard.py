import os
import select
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
        ui.warning(f"检测到单个配置文件中有多个 [Peer] 配置 (共 {len(parsed_peers)} 个)，本工具将生成多 Peer 出站")

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

def read_single_config_interactive(prompt_text: str) -> str:
    print(prompt_text, flush=True)
    lines = []
    fd = sys.stdin.fileno()
    while True:
        try:
            r, _, _ = select.select([sys.stdin], [], [], None)
            if not r:
                break
            line = sys.stdin.readline()
            if not line:
                break
            lines.append(line)
            if not line.strip():
                r2, _, _ = select.select([sys.stdin], [], [], 0.3)
                if not r2:
                    lines.pop()
                    break
        except KeyboardInterrupt:
            print()
            raise RuntimeError("用户取消了交互式输入")
    return "".join(lines).strip()

def read_wg_configs_interactive() -> list[str]:
    """交互式读取多个独立的 WireGuard 配置文件。"""
    env_configs = os.environ.get("WG_CONFIGS")
    if env_configs and env_configs.strip():
        ui.info("使用环境变量 WG_CONFIGS 中的多端点配置")
        return [c.strip() for c in env_configs.split("\n---\n") if c.strip()]
        
    env_content = os.environ.get("WG_CONFIG")
    if env_content and env_content.strip():
        ui.info("使用环境变量 WG_CONFIG 中的单端点配置")
        return [env_content.strip()]

    env_file = os.environ.get("WG_CONFIG_FILE")
    if env_file and env_file.strip():
        if os.path.exists(env_file):
            ui.info(f"使用环境变量 WG_CONFIG_FILE 指定的单端点文件: {env_file}")
            with open(env_file, 'r', encoding='utf-8') as f:
                return [f.read().strip()]
        else:
            ui.warning(f"WG_CONFIG_FILE 路径不存在: {env_file}")

    ui.section("WireGuard 配置")
    count_str = ui.prompt("你有几个配置文件？(默认 1)").strip()
    if not count_str or not count_str.isdigit():
        if count_str:
            ui.warning("无效的数量，将默认读取 1 个配置文件")
        count = 1
    else:
        count = int(count_str)
        if count < 1:
            ui.warning("数量必须大于等于 1，将默认读取 1 个配置文件")
            count = 1
            
    configs = []
    for i in range(count):
        while True:
            prompt_text = f"请粘贴第 {i+1}/{count} 个配置文件 (粘贴完成后按回车结束):"
            content = read_single_config_interactive(prompt_text)
            if not content:
                raise RuntimeError("配置内容不能为空")
            try:
                params = parse_wg_config(content)
                ui.success(f"✓ 第 {i+1} 个配置解析成功 (端点: {params['endpoint_host']}:{params['endpoint_port']})")
                configs.append(content)
                break
            except Exception as e:
                ui.warning(f"第 {i+1} 个配置解析失败: {e}")
                retry = ui.prompt(f"第 {i+1} 个配置解析失败，是否重新粘贴？(Y/n)").strip().lower()
                if retry in ("n", "no"):
                    raise RuntimeError(f"第 {i+1} 个配置解析失败且用户选择跳过") from e

    return configs

def read_wg_config_interactive() -> str:
    """交互式读取单个 WireGuard 配置。"""
    configs = read_wg_configs_interactive()
    if not configs:
        raise RuntimeError("未读取到任何 WireGuard 配置")
    return configs[0]

def build_singbox_wg_outbound(wg_params: dict, tag: str = "warp-out", allow_ipv6: bool = True, mtu: int = 1280) -> dict:
    """将解析后的参数转换为 sing-box WireGuard outbound。
    
    已知限制：若单个 .conf 文件内存在多个 [Peer] (通常不需要，Proton VPN 无此情况)，
    生成的 outbound 仍以第一个 Peer 的 Endpoint 作为公共根 server/server_port，
    此时多 Peer 的 per-peer endpoint 属性不会单独在 peer 对象中输出。
    """
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
