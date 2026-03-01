# Automated-sing-box-json-generator

由于本人头昏眼花看json看得好累，和ai一起vibecoding一个一键脚本
目前只提供 IP 更改，其他参数为默认值，主要为了方便自用。

# 🚀 Sing-box & WARP Watchdog 一键无痕部署

本工具旨在实现 **“云端存储脚本，本地无痕部署”**。每次运行都会生成一套全新的随机凭据，并自动配置 Watchdog 守护进程。

### ✨ 核心功能

* **随机强凭据生成**：自动生成 20 位密码，AnyTLS、TUIC、Hy2 分别独立。
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

1. **输入 IP**：脚本启动后会提示输入当前服务器 IP。
2. **依赖检查/安装**：自动检查并确保 `warp-go` 和 `sing-box` 可用。
3. **生成凭据**：调用 `sing-box` 生成 UUID 与 Reality KeyPair，并生成随机密码。
4. **写入配置**：
* 服务端配置：`/etc/sing-box/config.json`
* 守护脚本：`/root/warp_lazy_watchdog.sh`
5. **挂载定时任务**：每 60 秒执行一次 Watchdog，自动去重旧任务。
6. **重启与输出**：重启 `sing-box`，并在终端打印客户端 GUI JSON。

---

### 📁 项目结构（当前）

* `deploy.py`：核心部署流程（依赖检查、写配置、挂 watchdog、重启）
* `installer.py`：root 校验与依赖安装检查（warp-go / sing-box）
* `credentials.py`：动态生成 UUID、Reality 密钥与随机密码
* `config.py`：生成服务端/客户端配置 JSON（函数化）
* `watchdog.py`：写入 watchdog 脚本并挂载 crontab
* `main.py`：自举入口（每次启动都会刷新模块，再执行 `deploy.main()`）

---

### ⚠️ 安全提醒

* **Public 仓库安全**：脚本不硬编码固定密码
* **即时保存**：由于采用“无痕模式”，GUI JSON 仅在部署结束时显示一次，请务必及时保存。
