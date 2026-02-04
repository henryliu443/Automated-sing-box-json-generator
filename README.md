# Automated-sing-box-json-generator

由于本人头昏眼花看json看得好累，和ai一起vibecoding一个一键脚本
目前只提供ip更改 其他都是default 主要是为了方便我自己用

# 🚀 Sing-box & WARP Watchdog 一键无痕部署

本工具旨在实现 **“云端存储脚本，本地无痕部署”**。每次运行都会生成一套全新的安全凭据，并自动配置具备双重检测功能的 Watchdog 守护进程。

### ✨ 核心功能

* **1Password 级密码**：自动生成 20 位乱序强密码，AnyTLS、TUIC、Hy2 均使用独立凭据。
* **自动化 Watchdog**：集成双重检测逻辑（Ping 检测 + Cloudflare Trace 穿透检测），发现 WARP 掉线自动重连。
* **任务去重**：部署时自动清理旧的 `crontab` 任务，防止系统任务堆积。
* **顶级伪装**：严格继承 AnyTLS 8层 Padding Scheme 伪装策略。
* **无痕运行**：凭据仅在内存生成并打印，脚本本身不存储任何敏感信息。

---

### 📥 一键部署命令
在你的 VPS 终端执行以下命令：

```bash
curl -Ls "https://raw.githubusercontent.com/henryliu443/Automated-sing-box-json-generator/refs/heads/main/deploy.py" > deploy.py && python3 deploy.py && rm deploy.py
```
---

### 🛠️ 部署逻辑说明

1. **输入 IP**：脚本启动后会提示输入当前服务器 IP。
2. **生成凭据**：自动调用 `sing-box` 生成 UUID 和 Reality 密钥对。
3. **写入配置**：
* 服务端：`/etc/sing-box/config.json`
* 守护脚本：`/root/warp_lazy_watchdog.sh`


4. **挂载定时任务**：每 60 秒执行一次 Watchdog，自动去重旧任务。
5. **输出 JSON**：在终端直接打印客户端 GUI 配置，方便直接复制到软件中使用。

---

### ⚠️ 安全提醒

* **Public 仓库安全**：脚本不硬编码密码
* **即时保存**：由于采用“无痕模式”，GUI JSON 仅在部署结束时显示一次，请务必及时保存。
