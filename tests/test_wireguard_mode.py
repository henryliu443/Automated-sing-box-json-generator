import os
import unittest
from unittest.mock import patch, MagicMock

from automated_sing_box_generator.wireguard import parse_wg_config, build_singbox_wg_outbound
from automated_sing_box_generator.config import build_server_outbounds, build_server_config
from automated_sing_box_generator.watchdog import build_watchdog_script, deploy_watchdog
from automated_sing_box_generator.deploy import prompt_warp_mode
from automated_sing_box_generator.installer import ensure_warp
from automated_sing_box_generator.cli import build_parser, cmd_deploy

VALID_WG_CONFIG = """
[Interface]
PrivateKey = privatekeybase64=
Address = 10.2.0.2/32, fd00::2/128
DNS = 10.2.0.1, 1.1.1.1

[Peer]
PublicKey = peerpublickeybase64=
Endpoint = 185.200.118.4:51820
AllowedIPs = 0.0.0.0/0, ::/0
"""

VALID_WG_CONFIG_WITH_PRESHARED = """
[Interface]
PrivateKey = privatekeybase64=
Address = 10.2.0.2/32

[Peer]
PublicKey = peerpublickeybase64=
Endpoint = 185.200.118.4:51820
PresharedKey = presharedkeybase64=
"""

INVALID_WG_CONFIG = """
[Interface]
PrivateKey = privatekeybase64=

[Peer]
PublicKey = peerpublickeybase64=
"""

class TestWireGuardMode(unittest.TestCase):

    def setUp(self):
        self.orig_env = os.environ.get("WARP_MODE")
        self.orig_wg_config = os.environ.get("WG_CONFIG")
        self.orig_wg_configs = os.environ.get("WG_CONFIGS")
        self.orig_wg_config_file = os.environ.get("WG_CONFIG_FILE")
        if "WARP_MODE" in os.environ:
            del os.environ["WARP_MODE"]
        if "WG_CONFIG" in os.environ:
            del os.environ["WG_CONFIG"]
        if "WG_CONFIGS" in os.environ:
            del os.environ["WG_CONFIGS"]
        if "WG_CONFIG_FILE" in os.environ:
            del os.environ["WG_CONFIG_FILE"]

    def tearDown(self):
        if self.orig_env is not None:
            os.environ["WARP_MODE"] = self.orig_env
        elif "WARP_MODE" in os.environ:
            del os.environ["WARP_MODE"]
            
        if self.orig_wg_config is not None:
            os.environ["WG_CONFIG"] = self.orig_wg_config
        elif "WG_CONFIG" in os.environ:
            del os.environ["WG_CONFIG"]
            
        if self.orig_wg_configs is not None:
            os.environ["WG_CONFIGS"] = self.orig_wg_configs
        elif "WG_CONFIGS" in os.environ:
            del os.environ["WG_CONFIGS"]
            
        if self.orig_wg_config_file is not None:
            os.environ["WG_CONFIG_FILE"] = self.orig_wg_config_file
        elif "WG_CONFIG_FILE" in os.environ:
            del os.environ["WG_CONFIG_FILE"]

    def test_parse_wg_config_valid(self):
        params = parse_wg_config(VALID_WG_CONFIG)
        self.assertEqual(params["private_key"], "privatekeybase64=")
        self.assertEqual(params["address"], ["10.2.0.2/32", "fd00::2/128"])
        self.assertEqual(params["dns"], ["10.2.0.1", "1.1.1.1"])
        self.assertEqual(params["peer_public_key"], "peerpublickeybase64=")
        self.assertEqual(params["endpoint_host"], "185.200.118.4")
        self.assertEqual(params["endpoint_port"], 51820)
        self.assertEqual(params["allowed_ips"], ["0.0.0.0/0", "::/0"])

    def test_parse_wg_config_preshared(self):
        params = parse_wg_config(VALID_WG_CONFIG_WITH_PRESHARED)
        self.assertEqual(params["preshared_key"], "presharedkeybase64=")

    def test_parse_wg_config_invalid(self):
        with self.assertRaises(ValueError):
            parse_wg_config(INVALID_WG_CONFIG)

    def test_build_singbox_wg_outbound(self):
        params = parse_wg_config(VALID_WG_CONFIG_WITH_PRESHARED)
        outbound = build_singbox_wg_outbound(params, tag="custom-wg")
        self.assertEqual(outbound["type"], "wireguard")
        self.assertEqual(outbound["tag"], "custom-wg")
        self.assertEqual(outbound["server"], "185.200.118.4")
        self.assertEqual(outbound["server_port"], 51820)
        self.assertEqual(outbound["private_key"], "privatekeybase64=")
        self.assertEqual(outbound["peers"][0]["public_key"], "peerpublickeybase64=")
        self.assertEqual(outbound["peers"][0]["pre_shared_key"], "presharedkeybase64=")

    def test_build_server_outbounds_wireguard(self):
        params = parse_wg_config(VALID_WG_CONFIG)
        outbounds = build_server_outbounds("wireguard", wg_params=params)
        self.assertEqual(len(outbounds), 2)
        self.assertEqual(outbounds[0]["type"], "wireguard")
        self.assertEqual(outbounds[0]["tag"], "warp-out")
        self.assertEqual(outbounds[1]["type"], "direct")

    def test_build_server_outbounds_wireguard_missing_params(self):
        with self.assertRaises(ValueError):
            build_server_outbounds("wireguard", wg_params=None)

    def test_ensure_warp_wireguard(self):
        with patch("automated_sing_box_generator.ui.info") as mock_info:
            result = ensure_warp(preferred_mode="wireguard")
            self.assertEqual(result, "wireguard")
            mock_info.assert_called_once()

    def test_watchdog_script_wireguard(self):
        self.assertIsNone(build_watchdog_script("wireguard"))

    def test_deploy_watchdog_wireguard(self):
        with patch("subprocess.run") as mock_run:
            deploy_watchdog("/tmp/non_existent_watchdog.sh", warp_mode="wireguard")
            mock_run.assert_not_called()

    def test_prompt_warp_mode_env_wireguard(self):
        os.environ["WARP_MODE"] = "wireguard"
        self.assertEqual(prompt_warp_mode(), "wireguard")

    def test_prompt_warp_mode_env_wg(self):
        os.environ["WARP_MODE"] = "wg"
        self.assertEqual(prompt_warp_mode(), "wireguard")

    def test_prompt_warp_mode_interactive_wireguard(self):
        with patch("automated_sing_box_generator.ui.prompt", return_value="wireguard"):
            self.assertEqual(prompt_warp_mode(), "wireguard")

    def test_prompt_warp_mode_interactive_wg(self):
        with patch("automated_sing_box_generator.ui.prompt", return_value="wg"):
            self.assertEqual(prompt_warp_mode(), "wireguard")

    def test_cli_parser_deploy_warp_mode_wireguard(self):
        parser = build_parser()
        args = parser.parse_args(["deploy", "--warp-mode", "wireguard"])
        self.assertEqual(args.warp_mode, "wireguard")

        args_wg = parser.parse_args(["deploy", "--warp-mode", "wg"])
        self.assertEqual(args_wg.warp_mode, "wg")

    def test_cmd_deploy_warp_mode_wireguard(self):
        parser = build_parser()
        args = parser.parse_args(["deploy", "--warp-mode", "wireguard", "--wg-config", "dummy_config"])
        with patch("automated_sing_box_generator.deploy.main") as mock_main:
            mock_main.return_value = 0
            with self.assertRaises(SystemExit):
                cmd_deploy(args)
            self.assertEqual(os.environ.get("WARP_MODE"), "wireguard")
            self.assertEqual(os.environ.get("WG_CONFIG"), "dummy_config")

    def test_outbound_status_command(self):
        parser = build_parser()
        args = parser.parse_args(["manage", "outbound", "status"])
        self.assertEqual(args.command, "manage")
        self.assertEqual(args.manage_cmd, "outbound")
        self.assertEqual(args.outbound_cmd, "status")

    def test_outbound_switch_command(self):
        parser = build_parser()
        args = parser.parse_args(["manage", "outbound", "switch", "wireguard"])
        self.assertEqual(args.command, "manage")
        self.assertEqual(args.manage_cmd, "outbound")
        self.assertEqual(args.outbound_cmd, "switch")
        self.assertEqual(args.target, "wireguard")

    def test_filter_ipv6_allowed_ips(self):
        params = parse_wg_config(VALID_WG_CONFIG)
        outbound_v6 = build_singbox_wg_outbound(params, allow_ipv6=True)
        self.assertIn("::/0", outbound_v6["peers"][0]["allowed_ips"])
        
        outbound_no_v6 = build_singbox_wg_outbound(params, allow_ipv6=False)
        self.assertNotIn("::/0", outbound_no_v6["peers"][0]["allowed_ips"])
        self.assertEqual(outbound_no_v6["peers"][0]["allowed_ips"], ["0.0.0.0/0"])

    def test_parse_wg_config_multi_peer(self):
        multi_peer_config = """
[Interface]
PrivateKey = privatekeybase64=
Address = 10.2.0.2/32

[Peer]
PublicKey = peer1publickey=
Endpoint = 1.1.1.1:51820

[Peer]
PublicKey = peer2publickey=
Endpoint = 2.2.2.2:51820
"""
        params = parse_wg_config(multi_peer_config)
        self.assertEqual(len(params["peers"]), 2)
        self.assertEqual(params["peers"][0]["public_key"], "peer1publickey=")
        self.assertEqual(params["peers"][1]["public_key"], "peer2publickey=")
        self.assertEqual(params["peers"][0]["endpoint_host"], "1.1.1.1")
        self.assertEqual(params["peers"][1]["endpoint_host"], "2.2.2.2")

    def test_switch_outbound_warp_unavailable(self):
        from automated_sing_box_generator.outbound import switch_outbound
        with patch("os.path.exists", return_value=True), \
             patch("automated_sing_box_generator.installer.warp_proxy_ready", return_value=False), \
             patch("automated_sing_box_generator.installer.warp_tunnel_ready", return_value=False), \
             patch("automated_sing_box_generator.ui.error") as mock_error:
            switch_outbound("warp")
            mock_error.assert_called_with("WARP 服务未就绪/未运行！请先运行 'automated-sing-box-generator manage outbound add warp'。")

    def test_switch_outbound_wg_endpoint_unreachable(self):
        from automated_sing_box_generator.outbound import switch_outbound
        with patch("os.path.exists", return_value=True), \
             patch("automated_sing_box_generator.state.load_state", return_value={"wg_params": {"endpoint_host": "invalid-host-dns-fail.test"}}), \
             patch("automated_sing_box_generator.outbound.check_dns_resolvable", return_value=False), \
             patch("automated_sing_box_generator.ui.error") as mock_error:
            switch_outbound("wireguard")
            mock_error.assert_called_with("无法解析 WireGuard 终点 DNS: invalid-host-dns-fail.test，切换已终止。请检查网络连接。")

    def test_build_singbox_wg_outbound_custom_mtu(self):
        params = parse_wg_config(VALID_WG_CONFIG)
        outbound = build_singbox_wg_outbound(params, mtu=1420)
        self.assertEqual(outbound["mtu"], 1420)
        
        os.environ["WG_MTU"] = "1360"
        outbound_env = build_singbox_wg_outbound(params, mtu=1420)
        self.assertEqual(outbound_env["mtu"], 1360)

    def test_build_server_outbounds_single_wg(self):
        params = parse_wg_config(VALID_WG_CONFIG)
        outbounds = build_server_outbounds("wireguard", wg_params=params)
        self.assertEqual(len(outbounds), 2)
        self.assertEqual(outbounds[0]["type"], "wireguard")
        self.assertEqual(outbounds[0]["tag"], "warp-out")
        self.assertEqual(outbounds[1]["type"], "direct")

    def test_build_server_outbounds_multi_wg(self):
        p1 = parse_wg_config(VALID_WG_CONFIG)
        p2 = parse_wg_config(VALID_WG_CONFIG_WITH_PRESHARED)
        outbounds = build_server_outbounds("wireguard", wg_params=[p1, p2])
        self.assertEqual(len(outbounds), 4) # urltest + wg0 + wg1 + direct
        self.assertEqual(outbounds[0]["type"], "urltest")
        self.assertEqual(outbounds[0]["tag"], "warp-out")
        self.assertEqual(outbounds[0]["outbounds"], ["wg-out-0", "wg-out-1"])
        self.assertEqual(outbounds[1]["type"], "wireguard")
        self.assertEqual(outbounds[1]["tag"], "wg-out-0")
        self.assertEqual(outbounds[2]["type"], "wireguard")
        self.assertEqual(outbounds[2]["tag"], "wg-out-1")
        self.assertEqual(outbounds[3]["type"], "direct")

    def test_build_server_outbounds_wg_backcompat_dict(self):
        p = parse_wg_config(VALID_WG_CONFIG)
        # Verify single dict works perfectly (backwards compatible)
        outbounds = build_server_outbounds("wireguard", wg_params=p)
        self.assertEqual(len(outbounds), 2)
        self.assertEqual(outbounds[0]["type"], "wireguard")

    def test_read_wg_configs_interactive_env(self):
        from automated_sing_box_generator.wireguard import read_wg_configs_interactive
        os.environ["WG_CONFIG"] = VALID_WG_CONFIG
        configs = read_wg_configs_interactive()
        self.assertEqual(len(configs), 1)
        self.assertEqual(configs[0], VALID_WG_CONFIG.strip())

    def test_read_wg_configs_interactive_env_wg_configs(self):
        from automated_sing_box_generator.wireguard import read_wg_configs_interactive
        os.environ["WG_CONFIGS"] = f"{VALID_WG_CONFIG}\n---\n{VALID_WG_CONFIG_WITH_PRESHARED}"
        configs = read_wg_configs_interactive()
        self.assertEqual(len(configs), 2)
        self.assertEqual(configs[0], VALID_WG_CONFIG.strip())
        self.assertEqual(configs[1], VALID_WG_CONFIG_WITH_PRESHARED.strip())

    def test_cli_deploy_wg_config_multi(self):
        parser = build_parser()
        args = parser.parse_args(["deploy", "--warp-mode", "wireguard", "--wg-config", "dummy_conf1", "dummy_conf2"])
        with patch("automated_sing_box_generator.deploy.main") as mock_main:
            mock_main.return_value = 0
            with self.assertRaises(SystemExit):
                cmd_deploy(args)
            self.assertEqual(os.environ.get("WARP_MODE"), "wireguard")
            self.assertEqual(os.environ.get("WG_CONFIGS"), "dummy_conf1\n---\ndummy_conf2")

    def test_show_status_wireguard_multi(self):
        from automated_sing_box_generator.deploy import show_status
        p1 = parse_wg_config(VALID_WG_CONFIG)
        p2 = parse_wg_config(VALID_WG_CONFIG_WITH_PRESHARED)
        state_data = {
            "domain_root": "example.com",
            "enabled_protocols": ["anytls"],
            "active_outbound": "wireguard",
            "warp_mode": "wireguard",
            "wg_params": [p1, p2],
            "server_ip": "1.2.3.4",
            "deployed_at": "2026-08-11"
        }
        with patch("automated_sing_box_generator.state.load_state", return_value=state_data), \
             patch("automated_sing_box_generator.ui.kv") as mock_kv:
            show_status()
            mock_kv.assert_any_call("WireGuard 端点", "185.200.118.4:51820, 185.200.118.4:51820")

    def test_manage_outbound_add_wireguard_multi_wg_config(self):
        from automated_sing_box_generator.cli import cmd_outbound
        parser = build_parser()
        args = parser.parse_args(["manage", "outbound", "add", "wireguard", "--wg-config", "dummy_conf1", "dummy_conf2"])
        with patch("automated_sing_box_generator.outbound.add_outbound_profile") as mock_add:
            cmd_outbound(args)
            mock_add.assert_called_with("wireguard", wg_content="dummy_conf1\n---\ndummy_conf2")
