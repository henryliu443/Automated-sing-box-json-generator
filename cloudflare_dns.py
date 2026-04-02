"""Cloudflare DNS record management for automated subdomain provisioning."""

import json
import urllib.error
import urllib.parse
import urllib.request

import cli_ui as ui

CF_API_BASE = "https://api.cloudflare.com/client/v4"
MANAGED_COMMENT = "managed:sing-box-deploy"

IP_DETECT_URLS = [
    "https://api.ipify.org",
    "https://ipv4.icanhazip.com",
    "https://checkip.amazonaws.com",
]


def _cf_request(method, path, token, data=None):
    url = f"{CF_API_BASE}{path}"
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Cloudflare API {method} {path} → {e.code}:\n{err_body}"
        ) from e

    if not result.get("success"):
        errors = result.get("errors", [])
        msgs = "; ".join(err.get("message", str(err)) for err in errors)
        raise RuntimeError(f"Cloudflare API 失败: {msgs}")

    return result


# ---------------------------------------------------------------------------
# Public IP detection
# ---------------------------------------------------------------------------

def detect_public_ipv4():
    """Detect the server's public IPv4 address."""
    for url in IP_DETECT_URLS:
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "sing-box-deploy"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                ip = resp.read().decode("utf-8").strip()
            parts = ip.split(".")
            if len(parts) == 4 and all(
                p.isdigit() and 0 <= int(p) <= 255 for p in parts
            ):
                return ip
        except Exception:
            continue
    raise RuntimeError(
        "无法自动检测服务器公网 IPv4 地址，请检查网络连接"
    )


# ---------------------------------------------------------------------------
# DNS record CRUD
# ---------------------------------------------------------------------------

def _list_a_records(zone_id, token):
    """Fetch all A records in the zone."""
    records = []
    page = 1
    while True:
        path = f"/zones/{zone_id}/dns_records?type=A&page={page}&per_page=100"
        result = _cf_request("GET", path, token)
        records.extend(result.get("result", []))
        info = result.get("result_info", {})
        if page >= info.get("total_pages", 1):
            break
        page += 1
    return records


def _create_a_record(zone_id, token, name, ip):
    data = {
        "type": "A",
        "name": name,
        "content": ip,
        "ttl": 1,
        "proxied": False,
        "comment": MANAGED_COMMENT,
    }
    result = _cf_request("POST", f"/zones/{zone_id}/dns_records", token, data)
    return result["result"]["id"]


def _delete_record(zone_id, token, record_id):
    _cf_request("DELETE", f"/zones/{zone_id}/dns_records/{record_id}", token)


def _is_managed(record):
    return record.get("comment") == MANAGED_COMMENT


# ---------------------------------------------------------------------------
# High-level sync
# ---------------------------------------------------------------------------

def sync_dns_records(zone_id, token, desired_fqdns, server_ip,
                     old_record_ids=None):
    """Ensure exactly *desired_fqdns* have A records pointing to *server_ip*.

    1. Delete stale managed records stored from the previous deploy.
    2. Inspect all managed A records: fix wrong-IP, skip correct ones.
    3. Create missing records.

    Returns ``{fqdn: record_id}`` for persistence in state.
    """
    desired_set = set(desired_fqdns)

    # Phase 1 — delete previously-stored records that are no longer needed
    if old_record_ids:
        for fqdn, rid in list(old_record_ids.items()):
            if fqdn not in desired_set:
                try:
                    _delete_record(zone_id, token, rid)
                    ui.step(f"已删除旧 DNS 记录: {fqdn}")
                except RuntimeError:
                    ui.warning(f"删除旧记录失败 (可能已不存在): {fqdn}")

    # Phase 2 — scan existing managed A records
    all_a = _list_a_records(zone_id, token)
    managed = {r["name"]: r for r in all_a if _is_managed(r)}

    new_ids: dict[str, str] = {}

    for fqdn in desired_set:
        rec = managed.pop(fqdn, None)

        if rec and rec.get("content") == server_ip:
            ui.success(f"DNS 记录已存在: {fqdn} → {server_ip}")
            new_ids[fqdn] = rec["id"]
            continue

        if rec:
            ui.step(f"IP 变更，重建记录: {fqdn} ({rec['content']} → {server_ip})")
            try:
                _delete_record(zone_id, token, rec["id"])
            except RuntimeError:
                pass

        ui.step(f"创建 DNS A 记录: {fqdn} → {server_ip}")
        new_ids[fqdn] = _create_a_record(zone_id, token, fqdn, server_ip)

    # Phase 3 — purge leftover managed records we no longer need
    for name, rec in managed.items():
        try:
            _delete_record(zone_id, token, rec["id"])
            ui.step(f"清理无用 DNS 记录: {name}")
        except RuntimeError:
            ui.warning(f"清理记录失败: {name}")

    ui.success(f"DNS 同步完成 ({len(new_ids)} 条 A 记录)")
    return new_ids


def cleanup_all_managed_records(zone_id, token):
    """Remove every DNS record tagged with our managed comment."""
    all_a = _list_a_records(zone_id, token)
    managed = [r for r in all_a if _is_managed(r)]
    removed = 0
    for rec in managed:
        try:
            _delete_record(zone_id, token, rec["id"])
            ui.step(f"已删除: {rec['name']} → {rec['content']}")
            removed += 1
        except RuntimeError:
            ui.warning(f"删除失败: {rec['name']}")
    return removed
