import os
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from automated_sing_box_generator.deploy import (
    prompt_warp_mode,
    activate_server_config,
    deploy,
    redeploy,
    reconfigure,
    SING_BOX_CONFIG_PATH,
    SING_BOX_WARP_CONFIG_PATH,
    SING_BOX_DIRECT_CONFIG_PATH,
)
from automated_sing_box_generator.config import build_server_outbounds, build_server_config
from automated_sing_box_generator.watchdog import build_watchdog_script, deploy_watchdog


class TestWarpModeEmpirical(unittest.TestCase):
    """
    Empirical stress testing for direct (none) WARP mode implementation:
    1. Case sensitivity & whitespace trimming in prompt_warp_mode()
    2. Behavior when WARP_MODE environment variable is set vs unset
    3. Symlink target verification for activate_server_config()
    4. Flow integration symlink verification across deploy(), redeploy(), reconfigure()
    """

    def setUp(self):
        self.orig_env = os.environ.get("WARP_MODE")
        if "WARP_MODE" in os.environ:
            del os.environ["WARP_MODE"]
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        if self.orig_env is not None:
            os.environ["WARP_MODE"] = self.orig_env
        elif "WARP_MODE" in os.environ:
            del os.environ["WARP_MODE"]
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # Task 1: Case Sensitivity & Trimming in prompt_warp_mode()
    # -------------------------------------------------------------------------

    def test_prompt_warp_mode_interactive_case_and_trimming(self):
        test_cases = [
            ("DIRECT", "none"),
            ("none ", "none"),
            ("  direct  ", "none"),
            ("DiReCt", "none"),
            ("NONE", "none"),
            ("  NONE  ", "none"),
            ("proxy", "proxy"),
            ("  PROXY  ", "proxy"),
            ("TUN", "tun"),
            ("  tun  ", "tun"),
            ("", "proxy"),
            ("   ", "proxy"),
            ("INVALID_MODE", "proxy"),
        ]

        for input_val, expected in test_cases:
            with self.subTest(input_val=input_val, expected=expected):
                with patch("automated_sing_box_generator.ui.prompt", return_value=input_val):
                    res = prompt_warp_mode()
                    self.assertEqual(
                        res,
                        expected,
                        f"Input '{input_val}' should produce '{expected}', got '{res}'",
                    )

    # -------------------------------------------------------------------------
    # Task 2: Behavior when WARP_MODE env var is set vs unset
    # -------------------------------------------------------------------------

    def test_prompt_warp_mode_env_set_cases(self):
        test_cases = [
            ("DIRECT", "none"),
            ("none ", "none"),
            ("  direct  ", "none"),
            ("NONE", "none"),
            ("  NONE  ", "none"),
            ("PROXY", "proxy"),
            ("  proxy  ", "proxy"),
            ("TUN", "tun"),
            ("  tun  ", "tun"),
        ]

        for env_val, expected in test_cases:
            with self.subTest(env_val=env_val, expected=expected):
                os.environ["WARP_MODE"] = env_val
                res = prompt_warp_mode()
                self.assertEqual(
                    res,
                    expected,
                    f"WARP_MODE='{env_val}' should produce '{expected}', got '{res}'",
                )

    def test_prompt_warp_mode_env_unset_or_empty_falls_back_to_prompt(self):
        env_cases = [None, "", "   "]

        for env_val in env_cases:
            with self.subTest(env_val=env_val):
                if env_val is None:
                    if "WARP_MODE" in os.environ:
                        del os.environ["WARP_MODE"]
                else:
                    os.environ["WARP_MODE"] = env_val

                with patch("automated_sing_box_generator.ui.prompt", return_value="direct") as mock_prompt:
                    res = prompt_warp_mode()
                    mock_prompt.assert_called_once()
                    self.assertEqual(res, "none")

    def test_prompt_warp_mode_env_invalid_falls_back_to_prompt(self):
        os.environ["WARP_MODE"] = "invalid_mode_string"
        with patch("automated_sing_box_generator.ui.prompt", return_value="proxy") as mock_prompt:
            res = prompt_warp_mode()
            mock_prompt.assert_called_once()
            self.assertEqual(res, "proxy")

    # -------------------------------------------------------------------------
    # Task 3: Symlink Verification for activate_server_config()
    # -------------------------------------------------------------------------

    def test_activate_server_config_filesystem_symlink(self):
        target_direct = os.path.join(self.tmp_dir, "profiles", "config.direct.json")
        target_warp = os.path.join(self.tmp_dir, "profiles", "config.warp.json")
        link_path = os.path.join(self.tmp_dir, "config.json")

        os.makedirs(os.path.dirname(target_direct), exist_ok=True)
        with open(target_direct, "w") as f:
            f.write('{"mode": "direct"}')
        with open(target_warp, "w") as f:
            f.write('{"mode": "warp"}')

        # Activate direct config
        activate_server_config(target=target_direct, link_path=link_path)
        self.assertTrue(os.path.islink(link_path))
        self.assertEqual(os.readlink(link_path), target_direct)

        # Switch to warp config
        activate_server_config(target=target_warp, link_path=link_path)
        self.assertTrue(os.path.islink(link_path))
        self.assertEqual(os.readlink(link_path), target_warp)

        # Switch back to direct config
        activate_server_config(target=target_direct, link_path=link_path)
        self.assertTrue(os.path.islink(link_path))
        self.assertEqual(os.readlink(link_path), target_direct)

    def test_activate_server_config_overwrites_regular_file(self):
        target_direct = os.path.join(self.tmp_dir, "profiles", "config.direct.json")
        link_path = os.path.join(self.tmp_dir, "config.json")

        os.makedirs(os.path.dirname(target_direct), exist_ok=True)
        with open(target_direct, "w") as f:
            f.write('{"mode": "direct"}')
        with open(link_path, "w") as f:
            f.write('{"regular": "file"}')

        self.assertFalse(os.path.islink(link_path))
        activate_server_config(target=target_direct, link_path=link_path)
        self.assertTrue(os.path.islink(link_path))
        self.assertEqual(os.readlink(link_path), target_direct)

    # -------------------------------------------------------------------------
    # Task 3 (cont): Target Symlink Verification across deploy(), redeploy(), reconfigure()
    # -------------------------------------------------------------------------

    @patch("automated_sing_box_generator.deploy.print_port_snapshot")
    @patch("automated_sing_box_generator.deploy.restart_services_and_verify")
    @patch("automated_sing_box_generator.deploy.deploy_watchdog")
    @patch("automated_sing_box_generator.deploy.state_mod.save_state")
    @patch("automated_sing_box_generator.deploy.activate_server_config")
    @patch("automated_sing_box_generator.deploy.write_server_config")
    @patch("automated_sing_box_generator.deploy.build_client_config", return_value={})
    @patch("automated_sing_box_generator.deploy.build_server_config", return_value={})
    @patch("automated_sing_box_generator.deploy.generate_credentials", return_value={"uuid": "123"})
    @patch("automated_sing_box_generator.deploy.run_tls_issuance")
    @patch("automated_sing_box_generator.deploy.needs_tls_certificates", return_value=False)
    @patch("automated_sing_box_generator.deploy.ensure_dependencies")
    @patch("automated_sing_box_generator.deploy.sync_dns_records", return_value={})
    @patch("automated_sing_box_generator.deploy.prompt_server_ip", return_value="1.2.3.4")
    @patch("automated_sing_box_generator.deploy.prompt_protocol_specific_inputs", return_value={})
    @patch("automated_sing_box_generator.deploy.gen_subdomain_prefixes", return_value={"reality": "prefix1", "hy2": "prefix2"})
    @patch("automated_sing_box_generator.deploy.resolve_cf_dns_credentials", return_value=("token", "zone"))
    @patch("automated_sing_box_generator.deploy.prompt_warp_mode")
    @patch("automated_sing_box_generator.deploy.prompt_protocols", return_value=["anytls", "hy2"])
    @patch("automated_sing_box_generator.deploy.prompt_domain_root", return_value="example.com")
    def test_deploy_symlink_target_warp_none_vs_proxy(
        self, mock_domain, mock_proto, mock_warp_mode_fn, mock_cf, mock_prefixes,
        mock_proto_inputs, mock_ip, mock_dns, mock_deps, mock_certs, mock_tls,
        mock_creds, mock_build_srv, mock_build_cli, mock_write_srv,
        mock_activate_symlink, mock_save_state, mock_watchdog, mock_restart,
        mock_port_snap
    ):
        # Case A: warp_mode == "none"
        mock_warp_mode_fn.return_value = "none"
        mock_deps.return_value = "none"

        deploy(domain_root="example.com", enabled_protocols=["anytls", "hy2"])

        mock_activate_symlink.assert_called_with(target=SING_BOX_DIRECT_CONFIG_PATH)

        # Case B: warp_mode == "proxy"
        mock_activate_symlink.reset_mock()
        mock_warp_mode_fn.return_value = "proxy"
        mock_deps.return_value = "proxy"

        deploy(domain_root="example.com", enabled_protocols=["anytls", "hy2"])

        mock_activate_symlink.assert_called_with(target=SING_BOX_WARP_CONFIG_PATH)

    @patch("automated_sing_box_generator.deploy.print_port_snapshot")
    @patch("automated_sing_box_generator.deploy.restart_services_and_verify")
    @patch("automated_sing_box_generator.deploy.activate_server_config")
    @patch("automated_sing_box_generator.deploy.write_server_config")
    @patch("automated_sing_box_generator.deploy.build_client_config", return_value={})
    @patch("automated_sing_box_generator.deploy.build_server_config", return_value={})
    @patch("automated_sing_box_generator.deploy.generate_credentials", return_value={"uuid": "123"})
    @patch("automated_sing_box_generator.deploy.needs_tls_certificates", return_value=False)
    @patch("automated_sing_box_generator.deploy.sync_dns_records", return_value={})
    @patch("automated_sing_box_generator.deploy.gen_subdomain_prefixes", return_value={"reality": "prefix1", "hy2": "prefix2"})
    @patch("automated_sing_box_generator.deploy.resolve_cf_dns_credentials", return_value=("token", "zone"))
    @patch("automated_sing_box_generator.deploy.state_mod.load_state")
    @patch("automated_sing_box_generator.deploy.state_mod.save_state")
    def test_redeploy_symlink_target_warp_none_vs_proxy(
        self, mock_save_state, mock_load_state, mock_cf, mock_prefixes, mock_dns,
        mock_certs, mock_creds, mock_build_srv, mock_build_cli, mock_write_srv,
        mock_activate_symlink, mock_restart, mock_port_snap
    ):
        # Case A: saved warp_mode == "none"
        mock_load_state.return_value = {
            "domain_root": "example.com",
            "enabled_protocols": ["anytls", "hy2"],
            "warp_mode": "none",
            "anti_detection": {},
            "server_ip": "1.2.3.4",
        }

        redeploy(enabled_protocols=["anytls", "hy2"])
        mock_activate_symlink.assert_called_with(target=SING_BOX_DIRECT_CONFIG_PATH)

        # Case B: saved warp_mode == "proxy"
        mock_activate_symlink.reset_mock()
        mock_load_state.return_value["warp_mode"] = "proxy"

        redeploy(enabled_protocols=["anytls", "hy2"])
        mock_activate_symlink.assert_called_with(target=SING_BOX_WARP_CONFIG_PATH)

    @patch("automated_sing_box_generator.deploy.print_port_snapshot")
    @patch("automated_sing_box_generator.deploy.restart_services_and_verify")
    @patch("automated_sing_box_generator.deploy.activate_server_config")
    @patch("automated_sing_box_generator.deploy.write_server_config")
    @patch("automated_sing_box_generator.deploy.build_client_config", return_value={})
    @patch("automated_sing_box_generator.deploy.build_server_config", return_value={})
    @patch("automated_sing_box_generator.deploy.state_mod.load_state")
    @patch("automated_sing_box_generator.deploy.state_mod.save_state")
    def test_reconfigure_symlink_target_warp_none_vs_proxy(
        self, mock_save_state, mock_load_state, mock_build_srv, mock_build_cli,
        mock_write_srv, mock_activate_symlink, mock_restart, mock_port_snap
    ):
        # Case A: loaded warp_mode == "none"
        mock_load_state.return_value = {
            "credentials": {"uuid": "123"},
            "protocol_hosts": {"reality": "anytls.example.com", "hy2": "hy2.example.com"},
            "warp_mode": "none",
            "enabled_protocols": ["anytls", "hy2"],
            "server_ip": "1.2.3.4",
            "anti_detection": {},
        }

        reconfigure(enabled_protocols=["anytls", "hy2"])
        mock_activate_symlink.assert_called_with(target=SING_BOX_DIRECT_CONFIG_PATH)

        # Case B: loaded warp_mode == "proxy"
        mock_activate_symlink.reset_mock()
        mock_load_state.return_value["warp_mode"] = "proxy"

        reconfigure(enabled_protocols=["anytls", "hy2"])
        mock_activate_symlink.assert_called_with(target=SING_BOX_WARP_CONFIG_PATH)


if __name__ == "__main__":
    unittest.main()
