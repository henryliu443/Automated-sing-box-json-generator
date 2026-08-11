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
        if "WARP_MODE" in os.environ:
            del os.environ["WARP_MODE"]
        if "WG_CONFIG" in os.environ:
            del os.environ["WG_CONFIG"]

    def tearDown(self):
        if self.orig_env is not None:
            os.environ["WARP_MODE"] = self.orig_env
        elif "WARP_MODE" in os.environ:
            del os.environ["WARP_MODE"]
        if self.orig_wg_config is not None:
            os.environ["WG_CONFIG"] = self.orig_wg_config
        elif "WG_CONFIG" in os.environ:
            del os.environ["WG_CONFIG"]

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
