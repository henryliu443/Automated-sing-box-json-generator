# Automated-sing-box-json-generator

由于本人头昏眼花看json看得好累，和ai一起vibecoding一个一键脚本
当前默认采用三子域名 + SNI 分流（reality/hy2/tuic）结构，主要为了方便自用。

# 🚀 Sing-box & WARP Watchdog 一键无痕部署

本工具旨在实现 **“云端存储脚本，本地无痕部署”**。每次运行都会生成一套全新的随机凭据，并自动配置 Watchdog 守护进程。

### ✨ 核心功能

* **随机强凭据生成**：自动生成 20 位密码，AnyTLS、TUIC、Hy2 分别独立。
* **SNI 协议分层**：三协议默认绑定三子域名，客户端配置输出为域名直连（de-IP）。
* **伪装与接入分离**：Reality 使用独立握手伪装域名，连接域名仍为你的三条子域名。
* **证书自动签发**：自动为 TUIC/Hy2 子域名签发并安装 Let's Encrypt 证书（Cloudflare DNS-01）。
* **严格 TLS 校验**：客户端 TUIC/Hy2 默认启用证书严格校验（不再 `insecure`）。
* **端口冲突防护**：部署中自动检查 `23244/7443/9443` 端口归属；若使用 WARP 本地代理模式，额外检查 `40000`。
* **自动化 Watchdog**：集成双重检测逻辑（Ping 检测 + Cloudflare Trace 穿透检测），发现 WARP 掉线自动重连。
* **默认无日志落盘**：生成的 `sing-box` 配置默认关闭日志，Watchdog 也不再写入 `/var/log/warp_watchdog.log`。
* **官方 WARP 安装**：默认安装 Cloudflare 官方 `cloudflare-warp`（`warp-svc` + `warp-cli`），并初始化系统级 WARP 隧道模式（`set-mode warp`）。
* **WARP 双模式兼容**：自动识别 WARP 本地代理模式 (`127.0.0.1:40000`) 与系统隧道模式 (`warp-cli connect`)。
* **任务去重**：部署时自动清理旧的 `crontab` 任务，防止系统任务堆积。
* **配置模块化**：安装检查、凭据生成、配置生成、Watchdog 部署已拆分为独立模块。
* **无痕运行**：凭据仅在内存生成并打印，脚本本身不存储任何敏感信息。

---

### 📥 一键部署命令
在 VPS（`root` 用户）终端执行以下命令：

```bash
curl -Ls "https://raw.githubusercontent.com/henryliu443/Automated-sing-box-json-generator/refs/heads/main/main.py" > main.py && python3 main.py && rm main.py
```

或克隆仓库后直接运行：

```bash
python3 main.py
```

---

### 🛠️ 部署逻辑说明

1. **输入主域名**：脚本会提示输入主域名，自动生成三条协议子域名。
2. **依赖检查/安装**：自动检查并确保官方 Cloudflare WARP（`warp-svc` / `warp-cli`）、`sing-box` 可用，并自动识别 WARP 当前运行模式。
3. **签发证书**：通过 Cloudflare DNS-01 为 `tuic`/`hy2` 子域名签发证书。
4. **生成凭据**：调用 `sing-box` 生成 UUID 与 Reality KeyPair，并生成随机密码。
5. **写入配置**：
* 服务端配置：`/etc/sing-box/config.json`
* 守护脚本：`/root/warp_lazy_watchdog.sh`
6. **挂载定时任务**：每 60 秒执行一次 Watchdog，自动去重旧任务。
7. **重启与输出**：重启 `sing-box`，输出端口快照与客户端 GUI JSON。

---

### 📁 项目结构（当前）

* `deploy.py`：核心部署流程（依赖检查、写配置、挂 watchdog、重启）
* `installer.py`：root 校验与依赖安装检查（官方 `warp-svc` / `warp-cli`、WARP 本地代理 / 系统隧道、sing-box）
* `credentials.py`：动态生成 UUID、Reality 密钥与随机密码
* `config.py`：生成服务端/客户端配置 JSON（函数化）
* `certs.py`：Cloudflare DNS-01 证书签发与安装（TUIC/Hy2）
* `watchdog.py`：写入 watchdog 脚本并挂载 crontab
* `main.py`：自举入口（每次启动都会刷新模块，再执行 `deploy.main()`）

---

### ⚠️ 安全提醒

* **Public 仓库安全**：脚本不硬编码固定密码
* **即时保存**：由于采用“无痕模式”，GUI JSON 仅在部署结束时显示一次，请务必及时保存。

---

### 🔐 证书挑战方式说明

当前仅使用 **Cloudflare DNS-01 (`dns_cf`)**。

脚本支持两种方式提供凭据：

1. 运行时交互输入 `CF_Token` / `CF_Zone_ID`
2. 运行前导出环境变量（自动读取）

若你更喜欢环境变量方式，请在运行前导出：

```bash
export CF_Token="你的Cloudflare API Token"
export CF_Zone_ID="你的Zone ID"
```
