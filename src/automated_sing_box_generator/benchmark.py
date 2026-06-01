"""Benchmark module for testing proxy latency and download speed."""

import subprocess

from . import ui
from .installer import WARP_PROXY_URL, WARP_PROXY_PORT

# A fast and reliable endpoint to test TTFB
TEST_URL = "https://www.cloudflare.com/cdn-cgi/trace"
# A generic large file for speed test (Cloudflare speedtest)
SPEED_TEST_URL = "https://speed.cloudflare.com/__down?bytes=10485760" # 10MB

def _run_curl_benchmark(url, proxy=None):
    """Run curl and return (ttfb_ms, speed_bps)."""
    cmd = [
        "curl", "-s", "-o", "/dev/null",
        "-w", "%{time_starttransfer},%{speed_download}",
        "--connect-timeout", "10",
        "--max-time", "30"
    ]
    if proxy:
        cmd.extend(["-x", proxy])
    cmd.append(url)

    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0:
            parts = res.stdout.strip().split(",")
            if len(parts) == 2:
                ttfb = float(parts[0]) * 1000
                speed = float(parts[1])
                return ttfb, speed
    except Exception:
        pass
    return None, None


def _format_speed(bps):
    """Convert bytes per second to readable format."""
    if bps >= 1048576:
        return f"{bps / 1048576:.2f} MB/s"
    elif bps >= 1024:
        return f"{bps / 1024:.2f} KB/s"
    return f"{bps:.0f} B/s"


def run_benchmark():
    """Benchmark the network latency and speed."""
    ui.banner("Network Benchmark", "Testing latency and download speed...")

    ui.section("1. Direct Connection (No Proxy)")
    ui.step("Testing TTFB (Latency)...")
    dir_ttfb, _ = _run_curl_benchmark(TEST_URL)
    if dir_ttfb is not None:
        ui.success(f"Direct Latency (TTFB): {dir_ttfb:.2f} ms")
    else:
        ui.error("Failed to measure direct latency")

    ui.step("Testing Download Speed (10MB)...")
    _, dir_speed = _run_curl_benchmark(SPEED_TEST_URL)
    if dir_speed is not None:
        ui.success(f"Direct Speed: {_format_speed(dir_speed)}")
    else:
        ui.error("Failed to measure direct speed")

    ui.section(f"2. WARP Proxy ({WARP_PROXY_URL})")
    
    # Check if proxy port is listening
    try:
        res = subprocess.run(["ss", "-Hltnp"], stdout=subprocess.PIPE, text=True)
        if str(WARP_PROXY_PORT) not in res.stdout:
            ui.warning(f"WARP Proxy port {WARP_PROXY_PORT} does not appear to be listening.")
    except Exception:
        pass

    ui.step("Testing TTFB (Latency) via WARP...")
    proxy_ttfb, _ = _run_curl_benchmark(TEST_URL, proxy=WARP_PROXY_URL)
    if proxy_ttfb is not None:
        ui.success(f"WARP Latency (TTFB): {proxy_ttfb:.2f} ms")
    else:
        ui.error("Failed to measure WARP proxy latency")

    ui.step("Testing Download Speed (10MB) via WARP...")
    _, proxy_speed = _run_curl_benchmark(SPEED_TEST_URL, proxy=WARP_PROXY_URL)
    if proxy_speed is not None:
        ui.success(f"WARP Speed: {_format_speed(proxy_speed)}")
    else:
        ui.error("Failed to measure WARP proxy speed")

    ui.section("Benchmark Summary")
    if proxy_ttfb is not None and dir_ttfb is not None:
        overhead = proxy_ttfb - dir_ttfb
        ui.info(f"WARP Latency Overhead: {overhead:.2f} ms")
    
    if proxy_speed is not None and dir_speed is not None and dir_speed > 0:
        ratio = (proxy_speed / dir_speed) * 100
        ui.info(f"WARP Speed Ratio: {ratio:.1f}% of direct speed")
