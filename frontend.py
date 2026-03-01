import datetime
import os

from installer import run_cmd

SITE_ROOT = "/var/www/html"
INDEX_PATH = f"{SITE_ROOT}/index.html"
HEALTHZ_PATH = f"{SITE_ROOT}/healthz"
NGINX_FRONT_CONF = "/etc/nginx/conf.d/edge-front.conf"
DISABLE_CANDIDATES = [
    "/etc/nginx/conf.d/default.conf",
    "/etc/nginx/sites-enabled/default",
]

HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Edge Relay Matrix</title>
  <style>
    :root {
      --bg0: #0b1220;
      --bg1: #121a2b;
      --bg2: #1b2842;
      --fg0: #e8f0ff;
      --fg1: #99a9c9;
      --ok: #3ddc97;
      --warn: #ffc857;
      --line: rgba(255,255,255,0.09);
      --cyan: #33d6ff;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      color: var(--fg0);
      background:
        radial-gradient(circle at 15% 0%, rgba(51,214,255,0.15), transparent 30%),
        radial-gradient(circle at 85% 20%, rgba(61,220,151,0.14), transparent 32%),
        linear-gradient(145deg, var(--bg0), var(--bg1) 42%, var(--bg2));
      min-height: 100vh;
    }
    .wrap {
      max-width: 1100px;
      margin: 0 auto;
      padding: 24px 20px 38px;
    }
    h1 {
      font-size: 32px;
      letter-spacing: 0.02em;
      margin: 0;
      font-weight: 700;
    }
    .subtitle {
      margin-top: 8px;
      color: var(--fg1);
      font-size: 14px;
    }
    .grid {
      margin-top: 18px;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
      gap: 12px;
    }
    .card {
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 14px;
      background: rgba(255,255,255,0.03);
      backdrop-filter: blur(2px);
    }
    .card .label {
      color: var(--fg1);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }
    .card .value {
      margin-top: 8px;
      font-size: 24px;
      font-weight: 700;
    }
    .status {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      margin-top: 5px;
      font-size: 13px;
      color: var(--fg1);
    }
    .dot {
      width: 9px;
      height: 9px;
      border-radius: 50%;
      background: var(--ok);
      box-shadow: 0 0 10px rgba(61,220,151,0.85);
      animation: pulse 1.8s infinite;
    }
    @keyframes pulse {
      0% { transform: scale(0.92); opacity: 0.65; }
      50% { transform: scale(1.08); opacity: 1; }
      100% { transform: scale(0.92); opacity: 0.65; }
    }
    .panel {
      margin-top: 16px;
      border: 1px solid var(--line);
      border-radius: 14px;
      overflow: hidden;
      background: rgba(4,10,20,0.42);
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    th, td {
      padding: 11px 12px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      white-space: nowrap;
    }
    th { color: var(--fg1); font-weight: 500; }
    tr:last-child td { border-bottom: none; }
    .proto { color: var(--cyan); font-weight: 600; }
    .ok { color: var(--ok); font-weight: 600; }
    .warn { color: var(--warn); font-weight: 600; }
    .foot {
      margin-top: 14px;
      font-size: 12px;
      color: var(--fg1);
      display: flex;
      justify-content: space-between;
      gap: 10px;
      flex-wrap: wrap;
    }
    @media (max-width: 640px) {
      h1 { font-size: 26px; }
      .card .value { font-size: 21px; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Global Edge Relay Matrix</h1>
    <div class="subtitle">
      region: ap-east-1 / control plane: __DOMAIN_ROOT__ / updated: __UPDATED_AT__
    </div>

    <div class="grid">
      <div class="card">
        <div class="label">Current Throughput</div>
        <div class="value"><span id="egress">8.42</span> Tbps</div>
        <div class="status"><span class="dot"></span>Live aggregated edge egress</div>
      </div>
      <div class="card">
        <div class="label">Requests Per Second</div>
        <div class="value"><span id="rps">128640</span></div>
        <div class="status"><span class="dot"></span>Anycast ingress stabilized</div>
      </div>
      <div class="card">
        <div class="label">P95 RTT</div>
        <div class="value"><span id="rtt">38</span> ms</div>
        <div class="status"><span class="dot"></span>Inter-region route healthy</div>
      </div>
      <div class="card">
        <div class="label">Cache Hit Ratio</div>
        <div class="value"><span id="hit">99.18</span>%</div>
        <div class="status"><span class="dot"></span>Edge layer warmed</div>
      </div>
    </div>

    <div class="panel">
      <table>
        <thead>
          <tr>
            <th>Endpoint</th>
            <th>Protocol</th>
            <th>Queue</th>
            <th>Session State</th>
            <th>Health</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>__REALITY_HOST__</td>
            <td class="proto">reality</td>
            <td>178</td>
            <td>edge-flow</td>
            <td class="ok">Nominal</td>
          </tr>
          <tr>
            <td>__HY2_HOST__</td>
            <td class="proto">hysteria2</td>
            <td>253</td>
            <td>adaptive burst</td>
            <td class="ok">Nominal</td>
          </tr>
          <tr>
            <td>__TUIC_HOST__</td>
            <td class="proto">tuic</td>
            <td>212</td>
            <td>quic lane mux</td>
            <td class="ok">Nominal</td>
          </tr>
          <tr>
            <td>healthz</td>
            <td class="proto">http</td>
            <td>n/a</td>
            <td>synthetic probe</td>
            <td class="warn">Monitored</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="foot">
      <span>Edge Controller Build: 2026.03-lts</span>
      <span>Challenge path: /.well-known/acme-challenge/*</span>
      <span>This panel is static and intentionally lightweight.</span>
    </div>
  </div>
  <script>
    const state = {
      egress: 8.42,
      rps: 128640,
      rtt: 38,
      hit: 99.18
    };
    const pick = (n) => (Math.random() * n) - (n / 2);
    setInterval(() => {
      state.egress = Math.max(7.9, Math.min(9.6, state.egress + pick(0.12)));
      state.rps = Math.max(102000, Math.min(182000, Math.floor(state.rps + pick(1100))));
      state.rtt = Math.max(24, Math.min(66, Math.floor(state.rtt + pick(3.3))));
      state.hit = Math.max(97.6, Math.min(99.9, state.hit + pick(0.08)));
      document.getElementById("egress").textContent = state.egress.toFixed(2);
      document.getElementById("rps").textContent = String(state.rps);
      document.getElementById("rtt").textContent = String(state.rtt);
      document.getElementById("hit").textContent = state.hit.toFixed(2);
    }, 1400);
  </script>
</body>
</html>
"""

NGINX_CONF = """server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    root /var/www/html;
    index index.html;

    access_log /var/log/nginx/edge-front-access.log;
    error_log /var/log/nginx/edge-front-error.log warn;

    location = /healthz {
        default_type text/plain;
        return 200 "ok\\n";
    }

    location ^~ /.well-known/acme-challenge/ {
        default_type text/plain;
        root /var/www/html;
        try_files $uri =404;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
"""


def _render_index(domain_root, protocol_hosts):
    updated = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    page = HTML_TEMPLATE
    page = page.replace("__DOMAIN_ROOT__", domain_root)
    page = page.replace("__UPDATED_AT__", updated)
    page = page.replace("__REALITY_HOST__", protocol_hosts["reality"])
    page = page.replace("__HY2_HOST__", protocol_hosts["hy2"])
    page = page.replace("__TUIC_HOST__", protocol_hosts["tuic"])
    return page


def _disable_conflicts():
    for path in DISABLE_CANDIDATES:
        if not os.path.exists(path):
            continue
        disabled_path = f"{path}.disabled-by-singbox"
        if os.path.exists(disabled_path):
            if os.path.isfile(path) or os.path.islink(path):
                os.remove(path)
            continue
        os.rename(path, disabled_path)


def deploy_fake_frontend(domain_root, protocol_hosts):
    for key in ("reality", "hy2", "tuic"):
        if key not in protocol_hosts:
            raise RuntimeError(f"protocol_hosts 缺少 {key} 域名，无法部署前台网页")

    os.makedirs(SITE_ROOT, exist_ok=True)
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        f.write(_render_index(domain_root, protocol_hosts))
    with open(HEALTHZ_PATH, "w", encoding="utf-8") as f:
        f.write("ok\n")

    _disable_conflicts()
    with open(NGINX_FRONT_CONF, "w", encoding="utf-8") as f:
        f.write(NGINX_CONF)

    run_cmd("nginx -t")
    run_cmd("systemctl enable nginx")
    run_cmd("systemctl restart nginx")
