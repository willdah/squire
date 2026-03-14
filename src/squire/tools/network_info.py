"""network_info tool — interfaces, IPs, routes, DNS."""

import json
import platform

from ..system import LocalBackend

RISK_LEVEL = 1  # Info

_backend = LocalBackend()


async def network_info(include_routes: bool = False, include_dns: bool = False) -> str:
    """Get network interface information including IP addresses, MAC addresses, and link state.

    Args:
        include_routes: Also include the routing table.
        include_dns: Also include DNS resolver configuration.

    Returns a JSON object with interfaces, and optionally routes and dns fields.
    """
    info: dict = {}

    # Network interfaces
    if platform.system() == "Darwin":
        result = await _backend.run(["ifconfig"])
    else:
        result = await _backend.run(["ip", "-brief", "addr"])

    if result.returncode == 0:
        info["interfaces"] = result.stdout.strip()

    # Routes
    if include_routes:
        if platform.system() == "Darwin":
            route_result = await _backend.run(["netstat", "-rn"])
        else:
            route_result = await _backend.run(["ip", "route"])
        if route_result.returncode == 0:
            info["routes"] = route_result.stdout.strip()

    # DNS
    if include_dns:
        dns_result = await _backend.run(["cat", "/etc/resolv.conf"])
        if dns_result.returncode == 0:
            info["dns"] = dns_result.stdout.strip()

    return json.dumps(info, indent=2)
