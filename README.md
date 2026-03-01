# Automated-sing-box-json-generator

由于本人头昏眼花看json看得好累，和ai一起vibecoding一个一键脚本
当前默认采用三子域名 + SNI 分流（reality/hy2/tuic）结构，主要为了方便自用。

# 🚀 Sing-box & WARP Watchdog 一键无痕部署

本工具旨在实现 **“云端存储脚本，本地无痕部署”**。每次运行都会生成一套全新的随机凭据，并自动配置 Watchdog 守护进程。

### ✨ 核心功能

* **随机强凭据生成**：自动生成 20 位密码，AnyTLS、TUIC、Hy2 分别独立。
* **SNI 协议分层**：三协议默认绑定三子域名，客户端配置输出为域名直连（de-IP）。
* **伪装与接入分离**：Reality 使用独立握手伪装域名，连接域名仍为你的三条子域名。
* **证书自动签发**：自动为 TUIC/Hy2 子域名签发并安装 Let's Encrypt 证书（支持 DNS-01 / HTTP-01）。
* **严格 TLS 校验**：客户端 TUIC/Hy2 默认启用证书严格校验（不再 `insecure`）。
* **自动化 Watchdog**：集成双重检测逻辑（Ping 检测 + Cloudflare Trace 穿透检测），发现 WARP 掉线自动重连。
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

1. **输入主域名**：脚本会提示输入主域名（默认 `illuminatedhenry.shop`），自动生成三条协议子域名。
2. **依赖检查/安装**：自动检查并确保本地 WARP 代理（`127.0.0.1:40000`）和 `sing-box` 可用。
3. **签发证书**：自动选择 ACME 挑战方式并为 `tuic`/`hy2` 子域名签发证书。
4. **生成凭据**：调用 `sing-box` 生成 UUID 与 Reality KeyPair，并生成随机密码。
5. **写入配置**：
* 服务端配置：`/etc/sing-box/config.json`
* 守护脚本：`/root/warp_lazy_watchdog.sh`
6. **挂载定时任务**：每 60 秒执行一次 Watchdog，自动去重旧任务。
7. **重启与输出**：重启 `sing-box`，并在终端打印客户端 GUI JSON（已是域名版）。

---

### 📁 项目结构（当前）

* `deploy.py`：核心部署流程（依赖检查、写配置、挂 watchdog、重启）
* `installer.py`：root 校验与依赖安装检查（WARP 本地代理 / sing-box）
* `credentials.py`：动态生成 UUID、Reality 密钥与随机密码
* `config.py`：生成服务端/客户端配置 JSON（函数化）
* `certs.py`：ACME 证书签发与安装（TUIC/Hy2）
* `watchdog.py`：写入 watchdog 脚本并挂载 crontab
* `main.py`：自举入口（每次启动都会刷新模块，再执行 `deploy.main()`）

---

### ⚠️ 安全提醒

* **Public 仓库安全**：脚本不硬编码固定密码
* **即时保存**：由于采用“无痕模式”，GUI JSON 仅在部署结束时显示一次，请务必及时保存。

---

### 🔐 证书挑战方式说明

脚本会按以下顺序自动选择：

1. **Cloudflare DNS-01 (`dns_cf`)**：当检测到环境变量 `CF_Token` + `CF_Zone_ID` 时优先使用。
2. **HTTP-01 webroot**：当检测到 `80` 端口已监听且 webroot 目录 `/var/www/html` 存在时使用（适合 nginx 前台站）。
3. **HTTP-01 standalone**：仅在前两者都不满足时使用（需要可临时占用 80 端口，且外网可访问）。

若你计划用 nginx 作为假网页前台，建议确保：

* nginx 正在监听 `0.0.0.0:80`
* 站点根目录为 `/var/www/html`（或按需自行调整脚本中的 `ACME_WEBROOT`）
* 防火墙/安全组放行入站 TCP `80`

若统一采用 Cloudflare DNS-01，请先在运行前导出：

```bash
export CF_Token="你的Cloudflare API Token"
export CF_Zone_ID="你的Zone ID"
```
