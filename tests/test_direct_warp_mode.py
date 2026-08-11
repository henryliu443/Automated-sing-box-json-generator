import os
import unittest
from unittest.mock import patch

from automated_sing_box_generator.config import build_server_outbounds, build_server_config
from automated_sing_box_generator.watchdog import build_watchdog_script, deploy_watchdog
from automated_sing_box_generator.deploy import prompt_warp_mode, activate_server_config, show_status
from automated_sing_box_generator.installer import ensure_warp
from automated_sing_box_generator.cli import build_parser, cmd_deploy, cmd_watchdog


class TestDirectWarpMode(unittest.TestCase):

    def setUp(self):
        self.orig_env = os.environ.get("WARP_MODE")
        if "WARP_MODE" in os.environ:
            del os.environ["WARP_MODE"]

    def tearDown(self):
        if self.orig_env is not None:
            os.environ["WARP_MODE"] = self.orig_env
        elif "WARP_MODE" in os.environ:
            del os.environ["WARP_MODE"]

    def test_outbounds_none(self):
        outbounds = build_server_outbounds("none")
        self.assertEqual(outbounds, [{"type": "direct", "tag": "direct"}])

    def test_watchdog_script_none(self):
        self.assertIsNone(build_watchdog_script("none"))
        self.assertIsNotNone(build_watchdog_script("proxy"))
        self.assertIsNotNone(build_watchdog_script("tun"))

    def test_deploy_watchdog_none(self):
        with patch("subprocess.run") as mock_run:
            deploy_watchdog("/tmp/non_existent_watchdog.sh", warp_mode="none")
            mock_run.assert_not_called()

    def test_prompt_warp_mode_env_direct(self):
        os.environ["WARP_MODE"] = "direct"
        self.assertEqual(prompt_warp_mode(), "none")

    def test_prompt_warp_mode_env_none(self):
        os.environ["WARP_MODE"] = "none"
        self.assertEqual(prompt_warp_mode(), "none")

    def test_prompt_warp_mode_interactive_direct(self):
        with patch("automated_sing_box_generator.ui.prompt", return_value="direct"):
            self.assertEqual(prompt_warp_mode(), "none")

    def test_prompt_warp_mode_interactive_none(self):
        with patch("automated_sing_box_generator.ui.prompt", return_value="none"):
            self.assertEqual(prompt_warp_mode(), "none")

    def test_ensure_warp_none(self):
        with patch("automated_sing_box_generator.ui.info") as mock_info:
            result = ensure_warp(preferred_mode="none")
            self.assertEqual(result, "none")
            mock_info.assert_called_once()

    def test_cli_parser_deploy_warp_mode(self):
        parser = build_parser()
        args_direct = parser.parse_args(["deploy", "--warp-mode", "direct"])
        self.assertEqual(args_direct.warp_mode, "direct")

        args_none = parser.parse_args(["deploy", "--warp-mode", "none"])
        self.assertEqual(args_none.warp_mode, "none")

    def test_cmd_deploy_warp_mode_direct(self):
        parser = build_parser()
        args = parser.parse_args(["deploy", "--warp-mode", "direct"])
        with patch("automated_sing_box_generator.deploy.main") as mock_main:
            mock_main.return_value = 0
            with self.assertRaises(SystemExit):
                cmd_deploy(args)
            self.assertEqual(os.environ.get("WARP_MODE"), "none")

    def test_cmd_watchdog_none_mode(self):
        with patch("automated_sing_box_generator.state.load_state", return_value={"warp_mode": "none"}), \
             patch("automated_sing_box_generator.ui.info") as mock_info, \
             patch("automated_sing_box_generator.watchdog.deploy_watchdog") as mock_deploy:
            class DummyArgs:
                pass
            cmd_watchdog(DummyArgs())
            mock_info.assert_called_once()
            mock_deploy.assert_not_called()


if __name__ == "__main__":
    unittest.main()
