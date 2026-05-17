# Graph Report - .  (2026-05-17)

## Corpus Check
- 16 files · ~0 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 230 nodes · 429 edges · 15 communities detected
- Extraction: 53% EXTRACTED · 47% INFERRED · 0% AMBIGUOUS · INFERRED: 202 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## God Nodes (most connected - your core abstractions)
1. `deploy()` - 16 edges
2. `run_cmd()` - 11 edges
3. `configure_warpsvc_tunnel()` - 11 edges
4. `configure_warpsvc_proxy()` - 10 edges
5. `ensure_singbox()` - 10 edges
6. `reconfigure()` - 9 edges
7. `_tag()` - 9 edges
8. `ensure_warp()` - 8 edges
9. `ensure_dependencies()` - 8 edges
10. `make_qr_json_payload_plan()` - 8 edges

## Surprising Connections (you probably didn't know these)
- None detected - all connections are within the same source files.

## Communities

### Community 0 - "Community 0"
Cohesion: 0.11
Nodes (49): assert_port_allowed(), assert_port_required(), build_singbox_auto_update_script(), build_singbox_download_url(), command_exists(), configure_warpsvc_proxy(), configure_warpsvc_tunnel(), current_ssh_client_ip() (+41 more)

### Community 1 - "Community 1"
Cohesion: 0.13
Nodes (27): activate_server_config(), _clean_legacy_configs(), deploy(), _desired_fqdns(), main(), _merge_fingerprint_overrides(), normalize_domain_input(), _normalize_optional_input() (+19 more)

### Community 2 - "Community 2"
Cohesion: 0.15
Nodes (20): _build_anytls_client_outbound(), _build_anytls_server_inbound(), build_client_config(), build_client_outbounds(), build_domain_resolver(), _build_hy2_client_outbound(), _build_hy2_server_inbound(), build_protocol_hosts() (+12 more)

### Community 3 - "Community 3"
Cohesion: 0.18
Nodes (18): banner(), command(), divider(), error(), info(), json_block(), prompt(), Interactive protocol selection.      *available* is a list of ``(name, label)`` (+10 more)

### Community 4 - "Community 4"
Cohesion: 0.27
Nodes (12): _build_client_config_from_state(), decode_qr_json(), export_client_config(), export_json(), export_links(), export_qr(), export_qr_json(), _new_qr() (+4 more)

### Community 5 - "Community 5"
Cohesion: 0.17
Nodes (5): build_parser(), cmd_config(), cmd_deploy(), main(), _parse_protocols()

### Community 6 - "Community 6"
Cohesion: 0.25
Nodes (13): _cf_request(), cleanup_all_managed_records(), _create_a_record(), _delete_record(), detect_public_ipv4(), _is_managed(), _list_a_records(), Cloudflare DNS record management for automated subdomain provisioning. (+5 more)

### Community 7 - "Community 7"
Cohesion: 0.29
Nodes (12): _cert_is_valid_for_host(), _command_exists(), _ensure_dns_credentials(), _ensure_openssl(), ensure_tls_certificates(), _issue_and_install_cert(), _issue_cert(), needs_tls_certificates() (+4 more)

### Community 8 - "Community 8"
Cohesion: 0.27
Nodes (12): base45_decode(), base45_encode(), compact_json(), _decode_compressed_payload(), decode_qr_json_tokens(), _json_sha256(), make_qr_json_payload_plan(), _multipart_tokens() (+4 more)

### Community 9 - "Community 9"
Cohesion: 0.36
Nodes (7): command_exists(), deploy_killswitch_assets(), ensure_nftables(), Generate VPS VPN control-plane and kill-switch assets.  The installed assets kee, Install vpnctl and safety firewall assets without enabling VPN., run_cmd(), _write_file()

### Community 10 - "Community 10"
Cohesion: 0.32
Nodes (7): build_dns_config(), build_route_config(), _merge_unique(), 1.12.0+ 迁移重点：     - 增加 default_domain_resolver, Return a compact string summarising loaded rule counts., 1.12.0+ 迁移重点：     - 为拨号 DNS (如 DoH) 显式指定 domain_resolver, rule_summary()

### Community 11 - "Community 11"
Cohesion: 0.48
Nodes (6): has_state(), load_state(), _migrate_legacy(), Move state from the old path (inside sing-box config dir) to the new     isolate, _sanitize_json_value(), save_state()

### Community 12 - "Community 12"
Cohesion: 0.53
Nodes (5): gen_pwd(), gen_short_id(), gen_subdomain_prefix(), gen_subdomain_prefixes(), generate_credentials()

### Community 13 - "Community 13"
Cohesion: 0.33
Nodes (1): QRPayloadTests

### Community 14 - "Community 14"
Cohesion: 1.0
Nodes (0):

## Knowledge Gaps
- **27 isolated node(s):** `Run acme.sh --issue with real-time output.      Exit code 2 means cert already v`, `Return True if any of the enabled protocols requires a TLS certificate.`, `Cloudflare DNS record management for automated subdomain provisioning.`, `Detect the server's public IPv4 address.`, `Fetch all A records in the zone.` (+22 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 14`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Are the 15 inferred relationships involving `deploy()` (e.g. with `prompt_domain_root()` and `prompt_protocols()`) actually correct?**
  _`deploy()` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `run_cmd()` (e.g. with `ensure_system_cloudflare_dns()` and `ensure_ss_tool()`) actually correct?**
  _`run_cmd()` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `configure_warpsvc_tunnel()` (e.g. with `ensure_warp_package()` and `run_cmd()`) actually correct?**
  _`configure_warpsvc_tunnel()` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `configure_warpsvc_proxy()` (e.g. with `ensure_warp_package()` and `run_cmd()`) actually correct?**
  _`configure_warpsvc_proxy()` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `ensure_singbox()` (e.g. with `get_latest_singbox_version()` and `get_singbox_version()`) actually correct?**
  _`ensure_singbox()` has 9 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Run acme.sh --issue with real-time output.      Exit code 2 means cert already v`, `Return True if any of the enabled protocols requires a TLS certificate.`, `Cloudflare DNS record management for automated subdomain provisioning.` to the rest of the system?**
  _27 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.11 - nodes in this community are weakly interconnected._
