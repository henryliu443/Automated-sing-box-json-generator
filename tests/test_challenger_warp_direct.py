import os
import unittest
import tempfile
from unittest.mock import patch, MagicMock

from automated_sing_box_generator.installer import ensure_warp
from automated_sing_box_generator.watchdog import build_watchdog_script, deploy_watchdog
from automated_sing_box_generator.deploy import show_status


class TestEmpiricalChallengerWarpDirect(unittest.TestCase):

    # ------------------------------------------------------------------
    # Target 1: ensure_warp(preferred_mode="none")
    # ------------------------------------------------------------------
    def test_ensure_warp_none_early_return_and_no_warp_cli_calls(self):
        """Verify ensure_warp("none") returns "none", calls ui.info, and never calls warp-cli or readiness checks."""
        with patch("automated_sing_box_generator.ui.info") as mock_info, \
             patch("automated_sing_box_generator.installer.warp_proxy_ready") as mock_proxy_ready, \
             patch("automated_sing_box_generator.installer.warp_tunnel_ready") as mock_tun_ready, \
             patch("automated_sing_box_generator.installer.configure_warpsvc_proxy") as mock_cfg_proxy, \
             patch("automated_sing_box_generator.installer.configure_warpsvc_tunnel") as mock_cfg_tun, \
             patch("automated_sing_box_generator.installer.run_warp_cli") as mock_run_warp_cli, \
             patch("automated_sing_box_generator.installer.run_cmd") as mock_run_cmd:
            
            result = ensure_warp(preferred_mode="none")
            
            self.assertEqual(result, "none")
            mock_info.assert_called_once_with("WARP 模式为 direct (none)，跳过 WARP 安装与检查")
            mock_proxy_ready.assert_not_called()
            mock_tun_ready.assert_not_called()
            mock_cfg_proxy.assert_not_called()
            mock_cfg_tun.assert_not_called()
            mock_run_warp_cli.assert_not_called()
            mock_run_cmd.assert_not_called()

    def test_ensure_warp_proxy_executes_checks(self):
        """Verify ensure_warp("proxy") actually performs checks unlike "none" mode."""
        with patch("automated_sing_box_generator.ui.success") as mock_success, \
             patch("automated_sing_box_generator.installer.warp_proxy_ready", return_value=True) as mock_proxy_ready:
            
            result = ensure_warp(preferred_mode="proxy")
            
            self.assertEqual(result, "proxy")
            mock_proxy_ready.assert_called_once()
            mock_success.assert_called_once_with("检测到 WARP 本地代理模式 (127.0.0.1:40000)")

    def test_ensure_warp_invalid_mode_raises(self):
        """Verify ensure_warp raises RuntimeError for invalid mode."""
        with self.assertRaises(RuntimeError) as ctx:
            ensure_warp(preferred_mode="invalid_mode")
        self.assertIn("不支持的 WARP 模式: invalid_mode", str(ctx.exception))

    # ------------------------------------------------------------------
    # Target 2: build_watchdog_script("none") vs "proxy"/"tun"
    # ------------------------------------------------------------------
    def test_build_watchdog_script_none_returns_none(self):
        """Verify build_watchdog_script("none") returns None."""
        self.assertIsNone(build_watchdog_script("none"))

    def test_build_watchdog_script_proxy_returns_valid_script(self):
        """Verify build_watchdog_script("proxy") returns valid shell script with proxy check."""
        script = build_watchdog_script("proxy")
        self.assertIsInstance(script, str)
        self.assertIn("WARP_MODE=\"proxy\"", script)
        self.assertIn("tcp_connect \"$WARP_PROXY_HOST\"", script)
        self.assertIn("--proxy \"$WARP_PROXY\"", script)

    def test_build_watchdog_script_tun_returns_valid_script(self):
        """Verify build_watchdog_script("tun") returns valid shell script with tun check."""
        script = build_watchdog_script("tun")
        self.assertIsInstance(script, str)
        self.assertIn("WARP_MODE=\"tun\"", script)
        self.assertNotIn("--proxy \"$WARP_PROXY\"", script)
        self.assertIn("curl -fsS", script)

    def test_build_watchdog_script_invalid_mode_raises(self):
        """Verify build_watchdog_script raises ValueError for unsupported warp_mode."""
        with self.assertRaises(ValueError) as ctx:
            build_watchdog_script("unknown")
        self.assertIn("unsupported warp_mode: unknown", str(ctx.exception))

    # ------------------------------------------------------------------
    # Target 3: deploy_watchdog(warp_mode="none") no-op execution
    # ------------------------------------------------------------------
    def test_deploy_watchdog_none_noop(self):
        """Verify deploy_watchdog(warp_mode="none") makes no file or subprocess calls."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dummy_path = os.path.join(tmpdir, "watchdog.sh")
            with patch("subprocess.run") as mock_run, \
                 patch("builtins.open") as mock_open, \
                 patch("os.chmod") as mock_chmod:
                
                deploy_watchdog(script_path=dummy_path, warp_mode="none")
                
                mock_run.assert_not_called()
                mock_open.assert_not_called()
                mock_chmod.assert_not_called()
                self.assertFalse(os.path.exists(dummy_path))

    def test_deploy_watchdog_proxy_executes_deploy(self):
        """Verify deploy_watchdog(warp_mode="proxy") writes file and updates crontab."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dummy_path = os.path.join(tmpdir, "watchdog.sh")
            with patch("subprocess.run") as mock_run:
                deploy_watchdog(script_path=dummy_path, warp_mode="proxy")
                
                self.assertTrue(os.path.exists(dummy_path))
                mock_run.assert_called_once()
                cmd = mock_run.call_args[0][0]
                self.assertIn(dummy_path, cmd)
                self.assertIn("crontab", cmd)

    # ------------------------------------------------------------------
    # Target 4: show_status() output & warning suppression for none mode
    # ------------------------------------------------------------------
    def test_show_status_none_mode_kv_and_warning_suppression(self):
        """Verify show_status shows "direct (无 WARP)" and suppresses WARP readiness warning when warp_mode is none."""
        fake_state = {
            "domain_root": "example.com",
            "enabled_protocols": ["shadowsocks"],
            "warp_mode": "none",
            "server_ip": "1.2.3.4",
            "deployed_at": "2026-08-08 12:00:00 UTC",
        }
        with patch("automated_sing_box_generator.state.load_state", return_value=fake_state), \
             patch("automated_sing_box_generator.ui.kv") as mock_kv, \
             patch("automated_sing_box_generator.ui.info") as mock_info, \
             patch("automated_sing_box_generator.ui.warning") as mock_warning, \
             patch("automated_sing_box_generator.installer.get_singbox_version", return_value="1.8.0"), \
             patch("automated_sing_box_generator.installer.warp_proxy_ready") as mock_proxy_ready, \
             patch("automated_sing_box_generator.installer.warp_tunnel_ready") as mock_tun_ready:
            
            show_status()
            
            # Check KV output for WARP 模式
            mock_kv.assert_any_call("WARP 模式", "direct (无 WARP)")
            # Check info call for WARP status
            mock_info.assert_any_call("WARP: 直连模式 (无 WARP)")
            # Ensure readiness functions were not called
            mock_proxy_ready.assert_not_called()
            mock_tun_ready.assert_not_called()
            # Ensure no "WARP 未就绪" warning was emitted
            warning_messages = [call[0][0] for call in mock_warning.call_args_list]
            self.assertFalse(any("WARP 未就绪" in msg for msg in warning_messages))

    def test_show_status_proxy_mode_triggers_warning_if_not_ready(self):
        """Verify show_status displays warning when warp_mode is proxy but WARP is not ready."""
        fake_state = {
            "domain_root": "example.com",
            "enabled_protocols": ["shadowsocks"],
            "warp_mode": "proxy",
            "server_ip": "1.2.3.4",
            "deployed_at": "2026-08-08 12:00:00 UTC",
        }
        with patch("automated_sing_box_generator.state.load_state", return_value=fake_state), \
             patch("automated_sing_box_generator.ui.kv") as mock_kv, \
             patch("automated_sing_box_generator.ui.warning") as mock_warning, \
             patch("automated_sing_box_generator.installer.get_singbox_version", return_value="1.8.0"), \
             patch("automated_sing_box_generator.installer.warp_proxy_ready", return_value=False), \
             patch("automated_sing_box_generator.installer.warp_tunnel_ready", return_value=False):
            
            show_status()
            
            mock_kv.assert_any_call("WARP 模式", "proxy")
            warning_messages = [call[0][0] for call in mock_warning.call_args_list]
            self.assertTrue(any("WARP 未就绪" in msg for msg in warning_messages))


if __name__ == "__main__":
    unittest.main()
