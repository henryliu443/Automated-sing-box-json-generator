from __future__ import annotations
"""Cloudflare DNS record management for automated subdomain provisioning."""

import concurrent.futures
import json
import urllib.error
import urllib.parse
import urllib.request

from . import ui

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

def _check_ip(url):
    req = urllib.request.Request(url, headers={"User-Agent": "sing-box-deploy"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        ip = resp.read().decode("utf-8").strip()
    parts = ip.split(".")
    if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
        return ip
    raise ValueError("Invalid IP")

def detect_public_ipv4():
    """Detect the server's public IPv4 address using concurrent requests."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(IP_DETECT_URLS)) as executor:
        futures = {executor.submit(_check_ip, url): url for url in IP_DETECT_URLS}
        for future in concurrent.futures.as_completed(futures):
            try:
                return future.result()
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


def _delete_record(zone_id, token, record_id, fqdn_for_log=None):
    try:
        _cf_request("DELETE", f"/zones/{zone_id}/dns_records/{record_id}", token)
        if fqdn_for_log:
            ui.step(f"已删除 DNS 记录: {fqdn_for_log}")
    except RuntimeError as e:
        if fqdn_for_log:
            ui.warning(f"删除记录失败: {fqdn_for_log}")
        else:
            raise e


def _is_managed(record):
    return record.get("comment") == MANAGED_COMMENT


# ---------------------------------------------------------------------------
# High-level sync
# ---------------------------------------------------------------------------

def sync_dns_records(zone_id, token, desired_fqdns, server_ip,
                     old_record_ids=None):
    """Ensure exactly *desired_fqdns* have A records pointing to *server_ip*.

    Executes DNS creations and deletions concurrently for speed.
    """
    desired_set = set(desired_fqdns)
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        # Phase 1 — delete previously-stored records that are no longer needed
        futures_del = []
        if old_record_ids:
            for fqdn, rid in list(old_record_ids.items()):
                if fqdn not in desired_set:
                    futures_del.append(executor.submit(_delete_record, zone_id, token, rid, fqdn))
        
        concurrent.futures.wait(futures_del)

        # Phase 2 — scan existing managed A records
        all_a = _list_a_records(zone_id, token)
        managed = {r["name"]: r for r in all_a if _is_managed(r)}

        new_ids: dict[str, str] = {}
        futures_create = {}

        for fqdn in desired_set:
            rec = managed.pop(fqdn, None)

            if rec and rec.get("content") == server_ip:
                ui.success(f"DNS 记录已存在: {fqdn} → {server_ip}")
                new_ids[fqdn] = rec["id"]
                continue

            if rec:
                ui.step(f"IP 变更，重建记录: {fqdn} ({rec['content']} → {server_ip})")
                executor.submit(_delete_record, zone_id, token, rec["id"])

            ui.step(f"提交创建 DNS A 记录: {fqdn} → {server_ip}")
            futures_create[executor.submit(_create_a_record, zone_id, token, fqdn, server_ip)] = fqdn

        for future in concurrent.futures.as_completed(futures_create):
            fqdn = futures_create[future]
            try:
                new_ids[fqdn] = future.result()
            except RuntimeError as e:
                ui.warning(f"创建记录失败 {fqdn}: {e}")

        # Phase 3 — purge leftover managed records we no longer need
        futures_purge = []
        for name, rec in managed.items():
            futures_purge.append(executor.submit(_delete_record, zone_id, token, rec["id"], name))
            
        concurrent.futures.wait(futures_purge)

    ui.success(f"DNS 同步完成 ({len(new_ids)} 条 A 记录)")
    return new_ids


def cleanup_all_managed_records(zone_id, token):
    """Remove every DNS record tagged with our managed comment concurrently."""
    all_a = _list_a_records(zone_id, token)
    managed = [r for r in all_a if _is_managed(r)]
    
    removed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(_delete_record, zone_id, token, rec["id"], rec["name"]): rec for rec in managed}
        for future in concurrent.futures.as_completed(futures):
            if future.exception() is None:
                removed += 1
                
    return removed
