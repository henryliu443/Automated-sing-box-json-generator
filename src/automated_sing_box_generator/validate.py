"""Validation module for checking configuration integrity."""

import subprocess
import json

from . import ui
from . import state as state_mod
from .config import build_client_config

def run_validate():
    """Validate sing-box configuration and client config structure."""
    ui.banner("Configuration Validator", "Checking syntax and structural integrity...")

    has_errors = False

    ui.section("1. Server Configuration Check")
    ui.step("Executing: sing-box check -C /etc/sing-box")
    try:
        # Run sing-box built-in check
        res = subprocess.run(
            ["sing-box", "check", "-C", "/etc/sing-box"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        if res.returncode == 0:
            ui.success("Server configuration is valid")
            if res.stdout.strip():
                print(res.stdout.strip())
        else:
            ui.error("Server configuration validation failed!")
            print(res.stdout.strip())
            has_errors = True
    except FileNotFoundError:
        ui.error("sing-box executable not found")
        has_errors = True
    except Exception as e:
        ui.error(f"Error executing sing-box check: {e}")
        has_errors = True

    ui.section("2. Client Configuration Check")
    loaded = state_mod.load_state()
    if loaded:
        ui.step("State found, regenerating client config for validation")
        try:
            creds = loaded.get("credentials")
            phosts = loaded.get("protocol_hosts")
            enabled_protocols = loaded.get("enabled_protocols")
            server_ip = loaded.get("server_ip")
            opts = loaded.get("anti_detection")
            
            client_config = build_client_config(
                creds,
                protocol_hosts=phosts,
                enabled_protocols=enabled_protocols,
                server_ip=server_ip,
                fingerprint_opts=opts,
            )
            
            # Simple structural checks
            if "outbounds" not in client_config or not client_config["outbounds"]:
                ui.error("Client config is missing outbounds")
                has_errors = True
            elif "inbounds" not in client_config or not client_config["inbounds"]:
                ui.error("Client config is missing inbounds")
                has_errors = True
            else:
                # Test JSON serialization
                json.dumps(client_config)
                ui.success("Client configuration generated and structurally valid")
        except Exception as e:
            ui.error(f"Failed to generate or validate client config: {e}")
            has_errors = True
    else:
        ui.warning("No deployment state found. Skipping client configuration check.")

    ui.section("Validation Summary")
    if has_errors:
        ui.error("Configuration validation failed. Please check the errors above.")
    else:
        ui.success("All configuration checks passed!")
