# Automated-sing-box-json-generator

Sing-box + Cloudflare WARP 一键自动部署工具。

支持 AnyTLS (Reality) / TUIC / Hysteria2 三协议可选组合，自动完成依赖安装、DNS 记录创建、TLS 证书签发、配置生成、Watchdog 守护部署。

---

## 快速开始

### 推荐方式：通过 pip 安装

```bash
pip install automated-sing-box-generator
automated-sing-box-generator deploy
```

### 开发者方式：从源码运行

```bash
git clone https://github.com/henryliu443/Automated-sing-box-json-generator.git
cd Automated-sing-box-json-generator
pip install -e .
automated-sing-box-generator deploy
```

部署过程中会交互式提示输入：
1. 主域名（如 `example.com`）
2. Cloudflare API Token 和 Zone ID
3. 要启用的协议（默认全选）

---

## CLI 子命令

| 命令 | 说明 |
|------|------|
| `automated-sing-box-generator` | 无参数默认执行完整部署 |
| `automated-sing-box-generator deploy` | 完整部署（可选 `--domain` / `--protocols`） |
| `automated-sing-box-generator config` | 使用已保存的状态重新生成配置（可选 `--protocols` 切换协议） |
| `automated-sing-box-generator export` | 导出客户端配置（`--format json\|link\|qr\|qr-json`，`--output` 指定文件） |
| `automated-sing-box-generator decode-qr-json` | 还原 `qr-json` 压缩或分片二维码扫描结果 |
| `automated-sing-box-generator status` | 查看部署状态和服务健康度 |
| `automated-sing-box-generator vpn install/on/off/status/refresh` | 安装并控制 VPS 出站 Kill Switch（不管理 SSH 入站） |
| `automated-sing-box-generator install` | 仅安装依赖（WARP、sing-box） |
| `automated-sing-box-generator update` | 更新 sing-box 到最新版本 |
| `automated-sing-box-generator cleanup-dns` | 删除所有由本工具创建 of Cloudflare DNS 记录 |

### 示例

```bash
# 非交互式部署，仅启用 AnyTLS 和 TUIC
automated-sing-box-generator deploy --domain example.com --protocols anytls,tuic

# 导出分享链接
automated-sing-box-generator export --format link

# 导出客户端 JSON 到文件
automated-sing-box-generator export --format json --output client.json

# 导出二维码 (协议分享链接)
automated-sing-box-generator export --format qr

# 导出二维码 (完整 JSON 配置)
automated-sing-box-generator export --format qr-json

# 还原压缩/分片 qr-json 扫描结果
automated-sing-box-generator decode-qr-json --input scans.txt --output client.json

# 切换到仅 Hysteria2
automated-sing-box-generator config --protocols hy2
```

---

## 核心特性

### 协议可选化

部署时交互选择或通过 `--protocols` 指定要启用的协议组合：

- **AnyTLS (Reality)** — TCP，无需 TLS 证书，使用 Reality 伪装
- **TUIC** — UDP/QUIC，需要 TLS 证书
- **Hysteria2** — UDP/QUIC，需要 TLS 证书

仅启用 AnyTLS 时无需签发证书，部署更快。

### 路由模式（route-mode）

客户端配置内置三层出站架构，通过顶层 `route-mode` selector 在客户端 UI 一键切换：

| 模式 | 未匹配流量 | DNS（未匹配域名） | 推荐场景 |
|------|-----------|-------------------|---------|
| **route**（默认） | 直连 | 1.1.1.1 DoH via 代理 | 日常使用，规则分流 |
| **global** | 走代理节点（含 direct 规则） | 1.1.1.1 DoH via 代理 | 需要全局翻墙、测试连通性 |
| **direct** | 直连 | 1.1.1.1 DoH via 代理 | 临时关闭代理、排查网络问题 |

三层结构：

```
route-mode (selector)          ← route.final 指向这里
├── route   (direct)           ← 默认，规则分流
├── global  (selector)         ← 全局代理，可手动选节点或 proxy-auto
│   ├── proxy-auto (urltest)   ← 自动测速选最优
│   ├── anytls-out / tuic-out / hy2-out
│   └── route                  ← 兜底回退到直连
└── direct  (direct)           ← 全部直连
```

> **注意**：切到 `global` 时，分流规则的结果会收敛到代理出口（等价全局代理）；仅保留私网地址直连以保证局域网访问稳定。

**排查指南**：

| 现象 | 排查步骤 |
|------|---------|
| 全局模式下某些网站打不开 | 切到 `global` → 确认 `proxy-auto` 已选中且测速通过；若节点全挂，在 `global` 里手动切到 `route` 兜底 |
| 规则模式下国内网站走了代理 | 检查 `rules.json` 的 `direct_suffix` 是否包含该域名，或确认 GEOSITE-CN 规则集已下载 |
| DNS 解析慢 | DNS final 为 `dns-remote`（1.1.1.1 DoH via 代理），若代理延迟高会影响首次解析；已匹配的国内域名走 `dns-direct`（223.5.5.5）不受影响 |
| 想临时绕过大部分代理 | 切 `route-mode` → `direct`；显式 proxy 规则仍生效 |

### DNS 记录自动管理

部署时自动通过 Cloudflare API：
- 为每个协议生成**随机子域名前缀**（每次部署唯一，不在代码中硬编码）
- 检测服务器公网 IP
- 自动创建 A 记录，IP 变更时自动更新
- 协议切换时自动清理不再需要的记录
- 所有记录打上 `managed:sing-box-deploy` 标识，不会误删用户其他 DNS 记录

### 凭据安全

- 每次部署随机生成 UUID、Reality 密钥对、各协议独立密码、随机 short_id
- 凭据存储于 VPS 本地 `/etc/sing-box/deploy-state.json`（权限 `0600`，仅 root 可读）
- 服务端配置 `/etc/sing-box/config.json` 同样 `0600` 权限
- 代码仓库中不含任何硬编码凭据或子域名前缀
- `deploy-state.json` 已加入 `.gitignore`

### 客户端导出

- **JSON** — 完整 sing-box 客户端配置，可直接导入 GUI 客户端
- **Share Link** — 标准 URI 格式（`tuic://`、`hy2://`、`anytls://`）
- **QR Code** — 终端 ASCII 二维码，手机扫码导入。支持协议分享链接 (`--format qr`) 或完整 JSON 配置 (`--format qr-json`)。

#### 完整 JSON 二维码恢复格式

`export --format qr-json` 始终使用完整客户端 JSON，不会为了二维码容量省略路由规则或其他配置内容。输出策略自动选择：

1. 原始 JSON 能放入单个二维码时，直接输出可导入客户端的 JSON 二维码。
2. 原始 JSON 超出容量时，输出 `SBOX:ZLIB45` 载荷：完整 JSON 先用 zlib 压缩，再用 Base45 编码，便于二维码使用 alphanumeric 模式承载。
3. 压缩后仍超出单个二维码容量时，自动输出多个 `SBOX:ZLIB45` 分片二维码。每个分片包含序号、总数和 SHA-256 校验值，解码时会检查缺片、错片和内容损坏。

压缩或分片二维码不能直接导入普通 sing-box 客户端，需要先还原为 JSON。将扫码得到的每个 QR 文本按“一行一个”保存到 `scans.txt`，然后运行：

```bash
automated-sing-box-generator decode-qr-json --input scans.txt --output client.json
```

也可以从 stdin 读取：

```bash
cat scans.txt | automated-sing-box-generator decode-qr-json --input - --output client.json
```

### WARP 集成

- 自动安装官方 Cloudflare WARP（`warp-svc` + `warp-cli`）
- 自动识别本地代理模式（`127.0.0.1:40000`）与系统隧道模式
- 集成 Watchdog 守护脚本，每分钟检测 WARP 健康状态，自动重连/重注册

### VPS Kill Switch

部署时会安装 `vpnctl`、`vpn-safety-refresh` 与 `vpn-killswitch.service`，用于控制 VPS 主动出站流量：

```bash
vpnctl on
vpnctl status
vpnctl off
vpnctl refresh
```

控制结构：

```text
vpnctl
  ├── state machine
  ├── backend router       -> sing-box
  ├── firewall controller  -> nft
  └── health monitor       -> WARP / sing-box / firewall
```

设计约束：

- 不修改 sshd 配置
- 不限制 SSH 来源 IP
- 不修改 input 默认策略
- 只创建独立 nftables 表 `inet vpnks`
- `engage.cloudflareclient.com` 会在 VPS 上解析后写入 nft set
- VPN 状态只由 `vpnctl` 输出，nft/systemd/sing-box 不参与状态决策
- VPN 异常时普通公网出站会被阻断，但 SSH 入站/回包保持放行

### 其他

- TLS 证书通过 acme.sh + Cloudflare DNS-01 自动签发和续签
- sing-box 自动更新定时任务（每日凌晨检查 GitHub Latest Release）
- 端口冲突自动检测
- 部署状态持久化，支持重新生成配置和导出而无需重新部署

---

## 部署流程

```
输入主域名 + CF 凭据 + 选择协议
        │
        ▼
  生成随机子域名前缀
        │
        ▼
  检测服务器公网 IP → Cloudflare API 创建 A 记录
        │
        ▼
  安装依赖 (WARP + sing-box) + 端口检查
        │
        ▼
  签发 TLS 证书 (仅 TUIC/Hy2 需要)
        │
        ▼
  生成随机凭据 → 写入服务端配置 + 保存部署状态
        │
        ▼
  部署 Watchdog → 重启 sing-box → 输出客户端配置
```

---

## 项目结构

| 文件 | 说明 |
|------|------|
| `cli.py` | CLI 入口，argparse 子命令分发 |
| `deploy.py` | 核心部署/重配置/状态查看流程 |
| `config.py` | 服务端/客户端 sing-box 配置生成（按协议动态组装） |
| `cloudflare_dns.py` | Cloudflare API DNS 记录管理（创建/更新/清理） |
| `credentials.py` | UUID、Reality 密钥、随机密码、子域名前缀生成 |
| `certs.py` | acme.sh + Cloudflare DNS-01 证书签发 |
| `installer.py` | WARP、sing-box 安装与端口检查 |
| `state.py` | 部署状态持久化（`/etc/sing-box/deploy-state.json`） |
| `export.py` | 客户端配置导出（JSON / Share Link / QR） |
| `watchdog.py` | WARP Watchdog 脚本生成与 crontab 挂载 |
| `route_profile.py` | 客户端路由规则与 DNS 配置 |
| `ui.py` | 终端 UI 输出函数 |
| `killswitch.py` | VPS Kill Switch 控制逻辑 |

---

## Cloudflare 凭据

需要一个具有 **DNS 编辑权限** 的 Cloudflare API Token 和对应的 Zone ID。

提供方式（二选一）：

1. **运行时交互输入**（部署时会自动提示）
2. **环境变量**（运行前导出）：

```bash
export CF_Token="你的 Cloudflare API Token"
export CF_Zone_ID="你的 Zone ID"
```

这些凭据**不会被持久化到磁盘**，仅在部署过程中使用。

---

## 安全说明

本项目设计为公开仓库安全存储：

- 所有敏感数据（密码、私钥、子域名前缀）在部署时动态生成，存储于 VPS 的 `0600` 文件中
- 代码中不含任何硬编码凭据
- Cloudflare API Token 仅在内存中使用，不写入磁盘
- DNS 记录通过 API comment 标识，清理时不会误删用户其他记录
