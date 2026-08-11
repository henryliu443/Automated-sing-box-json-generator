# 多 Proton 端点一键部署计划

## 设计目标

```
manage outbound switch warp        → Cloudflare WARP
manage outbound switch wireguard   → Proton VPN (自动选最优端点)
manage outbound switch direct      → VPS 直连
```

WARP 和 Proton 之间是 **profile 级切换**（symlink + `systemctl restart`）。
Proton 的多个端点之间是 **自动故障切换**（sing-box `urltest` outbound，每 5 分钟测速选最优）。

用户只需一次粘贴（N 个 `.conf`），工具自动生成 `urltest` 包裹的 N 个 WireGuard 出站。

---

## 核心设计：数据流

```
交互式输入:
  "你有几个配置文件？" → 3
  paste config #1 ^D  →  parse_wg_config()  →  wg_params_1
  paste config #2 ^D  →  parse_wg_config()  →  wg_params_2
  paste config #3 ^D  →  parse_wg_config()  →  wg_params_3

                  ↓
          wg_params: list[dict]
                  ↓
    build_server_outbounds("wireguard", wg_params)
                  ↓
┌─────────────────────────────────────────────────┐
│ {                                               │
│   "type": "urltest",                            │
│   "tag": "warp-out",          ← 路由不变        │
│   "outbounds": ["wg-out-0","wg-out-1","wg-out-2"]│
│   "url": "https://cp.cloudflare.com/generate_204",│
│   "interval": "5m",                             │
│   "tolerance": 100                              │
│ },                                              │
│ { "type": "wireguard", "tag": "wg-out-0", ... },│
│ { "type": "wireguard", "tag": "wg-out-1", ... },│
│ { "type": "wireguard", "tag": "wg-out-2", ... },│
│ { "type": "direct",     "tag": "direct" }       │
└─────────────────────────────────────────────────┘
```

**关键**: `urltest` 的 tag 是 `"warp-out"`，和现有的单 WARP / 单 WG 场景保持一致。所有入站路由规则指向 `"warp-out"`，完全不需要改。

---

## 改动文件清单（6 个）

### 1. `wireguard.py` — 新增 `read_wg_configs_interactive()`

**不改**已有的 `parse_wg_config`、`build_singbox_wg_outbound`、`read_wg_config_interactive`（保留给旧路径 `--wg-config` 单文件）。

新增函数：

```python
def read_wg_configs_interactive() -> list[str]:
    """交互式读取多个独立的 WireGuard 配置文件。

    Proton VPN 每个服务器一个 .conf，各有不同的 PrivateKey。
    先问数量，再逐个粘贴。

    环境变量支持:
      - WG_CONFIG: 单个配置内容（兼容旧行为）
      - WG_CONFIG_FILE: 单个文件路径（兼容旧行为）
      - WG_CONFIGS: 多个配置内容，用 \\n---\\n 分隔（CI / 脚本模式）
    """
```

交互式 UX：

```
┌─────────────────────────────────────────────┐
│  WireGuard 配置                              │
├─────────────────────────────────────────────┤
│  你有几个配置文件？> 3                       │
│  请粘贴第 1/3 个配置文件 (Ctrl+D 结束):      │
│  {{ paste .conf #1 }}                       │
│  ^D                                         │
│  ✓ 端点: 185.x.x.1:51820                    │
│  ...                                        │
└─────────────────────────────────────────────┘
```

### 2. `config.py` — `build_server_outbounds` 多 conf 分支

只改 `build_server_outbounds(warp_mode, wg_params, mtu)` 中 `wireguard` 分支：

```python
if warp_mode == "wireguard":
    if not wg_params:
        raise ValueError("wireguard mode requires wg_params")
    # 向后兼容旧 dict 格式
    wg_list = wg_params if isinstance(wg_params, list) else [wg_params]

    from .wireguard import build_singbox_wg_outbound

    if len(wg_list) == 1:
        # 单端点：行为完全不变
        return [
            build_singbox_wg_outbound(wg_list[0], tag="warp-out",
                                      allow_ipv6=False, mtu=mtu),
            {"type": "direct", "tag": "direct"},
        ]

    # 多端点：生成 urltest + N 个 wireguard outbound
    tags = [f"wg-out-{i}" for i in range(len(wg_list))]
    wg_outbounds = [
        build_singbox_wg_outbound(p, tag=t, allow_ipv6=False, mtu=mtu)
        for p, t in zip(wg_list, tags)
    ]
    return [
        {
            "type": "urltest",
            "tag": "warp-out",
            "outbounds": tags,
            "url": "https://cp.cloudflare.com/generate_204",
            "interval": "5m",
            "tolerance": 100,
            "interrupt_exist_connections": True,
        },
        *wg_outbounds,
        {"type": "direct", "tag": "direct"},
    ]
```

### 3. `deploy.py` — 5 处改动

#### 3a. `deploy()` — 读多 conf

```python
# L271-276
if preferred_warp_mode == "wireguard":
    from .wireguard import read_wg_configs_interactive, parse_wg_config
    configs = read_wg_configs_interactive()
    wg_params = [parse_wg_config(c) for c in configs]
    endpoints = ", ".join(p["endpoint_host"] for p in wg_params)
    ui.success(f"已加载 {len(wg_params)} 个 WireGuard 端点: {endpoints}")
```

#### 3b. `deploy()` — state 保存

```python
# L354-367: wg_params 现在是 list，直接序列化
"wg_params": wg_params,  # list[dict]
```

#### 3c. `redeploy()` — 读 state 中的 list

```python
# L391: 不变！state 里存的就是 list，直接 .get("wg_params")
wg_params = old_state.get("wg_params")
```

#### 3d. `reconfigure()` — 同理

```python
# L485: 不变
wg_params = loaded.get("wg_params")
```

#### 3e. `show_status()` — 显示多端点

```python
if active == "wireguard":
    wg_p = loaded.get("wg_params")
    if isinstance(wg_p, list):
        endpoints = [f"{p['endpoint_host']}:{p['endpoint_port']}" for p in wg_p]
        ui.kv("WireGuard 端点", ", ".join(endpoints))
    elif isinstance(wg_p, dict):
        ui.kv("WireGuard 端点",
              f"{wg_p.get('endpoint_host')}:{wg_p.get('endpoint_port')}")
```

### 4. `outbound.py` — `add_outbound_profile` 改读取

```python
# L175-191
if outbound_type == "wireguard":
    from .wireguard import read_wg_configs_interactive, parse_wg_config
    if wg_content:
        # CLI 直传内容（环境变量 / --wg-config）
        wg_params = [parse_wg_config(wg_content)]
    else:
        configs = read_wg_configs_interactive()
        wg_params = [parse_wg_config(c) for c in configs]
```

### 5. `cli.py` — `--wg-config` 支持多文件

```python
# deploy 参数
p_deploy.add_argument("--wg-config", nargs="*", default=None,
                      help="WireGuard 配置文件路径 (可多个)")

# manage outbound add 参数
p_ob_add.add_argument("--wg-config", nargs="*", default=None,
                      help="WireGuard 配置文件路径 (可多个)")

# cmd_deploy 处理
wg_configs = getattr(args, "wg_config", None)
if wg_configs:
    import json
    configs = []
    for c in wg_configs:
        if os.path.isfile(c):
            with open(c, 'r', encoding='utf-8') as f:
                configs.append(f.read().strip())
        else:
            configs.append(c.strip())
    os.environ["WG_CONFIGS"] = "\n---\n".join(configs)
```

### 6. 测试 — `tests/test_wireguard_mode.py`

| # | 测试 | 验证 |
|---|---|---|
| 1 | `test_build_server_outbounds_single_wg` | 单 conf → 1 wg outbound + direct（回归） |
| 2 | `test_build_server_outbounds_multi_wg` | 2 confs → urltest + 2 wg + direct |
| 3 | `test_build_server_outbounds_multi_wg_three` | 3 confs → urltest + 3 wg + direct |
| 4 | `test_build_server_outbounds_wg_backcompat_dict` | 旧 dict 格式仍工作 |
| 5 | `test_read_wg_configs_interactive_env` | WG_CONFIG 单文件兼容 |
| 6 | `test_read_wg_configs_interactive_env_wg_configs` | WG_CONFIGS 多文件 `---` 分隔 |
| 7 | `test_cli_deploy_wg_config_multi` | `--wg-config a.conf b.conf` |
| 8 | `test_show_status_wireguard_multi` | 多端点状态显示 |

---

## 不改的文件

| 文件 | 原因 |
|---|---|
| `state.py` | JSON 序列化天然支持 list |
| `watchdog.py` | wireguard 模式已跳过 watchdog |
| `doctor.py` | wireguard 健康检查不变 |
| `uninstall.py` | 删除 `/etc/sing-box/` 已覆盖 profiles 目录 |
| `installer.py` | `ensure_warp("wireguard")` 已正确处理 |
| 已有 `parse_wg_config` | 单 conf 解析逻辑完全复用 |
| 已有 `build_singbox_wg_outbound` | 单 outbound 生成逻辑完全复用 |

---

## 完整 CLI 操作矩阵

```bash
# ── 首次部署（交互式粘贴 3 个 Proton .conf）──
automated-sing-box-generator deploy --warp-mode wireguard
# 你有几个配置文件？> 3
# 粘贴 #1 ^D → 粘贴 #2 ^D → 粘贴 #3 ^D
# → 生成 config.wireguard.json (urltest + 3 wg outbound)
# → 生成 config.direct.json
# → 自动激活 wireguard profile

# ── 非交互式（CI / 脚本）──
automated-sing-box-generator deploy --warp-mode wireguard \
    --wg-config ~/proton-jp.conf ~/proton-nl.conf ~/proton-us.conf

# ── 查看出口状态 ──
automated-sing-box-generator manage outbound status
#   活跃出口: wireguard
#   WireGuard 端点: 185.x.1.4:51820, 185.x.2.5:51820, 185.x.3.6:51820

# ── 即时切换 ──
automated-sing-box-generator manage outbound switch warp       # → Cloudflare IP
automated-sing-box-generator manage outbound switch wireguard  # → Proton IP (自动最优)
automated-sing-box-generator manage outbound switch direct     # → VPS IP

# ── 更新 Proton 端点（替换全部）──
automated-sing-box-generator manage outbound add wireguard
# 你有几个配置文件？> 2
# → 覆盖 config.wireguard.json
# → 如果当前活跃，即时重启生效

# ── 重新生成凭据（wg_params 保留，端点不变）──
automated-sing-box-generator config --api
# → UUID/密码/Reality 全部重新生成
# → wg_params 列表完整保留

# ── 调整配置（所有 profile 用新凭据重建）──
automated-sing-box-generator config
# → 所有凭据从 state 读取
# → config.wireguard.json / config.warp.json / config.direct.json 全部重建
```

---

## 自动故障切换行为

```
                ┌──────────────────┐
                │  urltest          │
                │  tag: warp-out    │
                │  interval: 5m     │
                └───┬───┬───┬───────┘
                    │   │   │
            ┌───────┘   │   └───────┐
            ▼           ▼           ▼
      wg-out-0    wg-out-1    wg-out-2
      Proton JP   Proton NL   Proton US
      .conf #1    .conf #2    .conf #3

每 5 分钟测速 https://cp.cloudflare.com/generate_204:
  - 选中 RTT 最低的端点
  - tolerance=100ms: 新端点需比当前快 100ms 才切换（防止抖动）
  - 端点挂了: urltest 自动跳过不可达的
```

---

## 向后兼容保证

| 场景 | 行为 |
|---|---|
| 旧 state（`wg_params: dict`） | `build_server_outbounds` 自动检测 `isinstance(list)`，包装为 `[dict]` |
| 旧 `--wg-config` 单文件 | `read_wg_configs_interactive` 检测到环境变量时返回 `[content]` |
| 旧 `deploy()` 单 conf 粘贴 | 问"几个？"输 1，流程完全相同 |
