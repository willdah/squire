"""network_info tool — interfaces, IPs, routes, DNS."""

import json
import platform

from ._effects import Effect
from ._registry import get_registry

RISK_LEVEL = 1  # Info
EFFECT: Effect = "read"


def _get_os_type(backend, host: str) -> str:
    """Determine the OS type for the target host."""
    if host == "local":
        return platform.system()
    return getattr(backend, "os_type", "Linux")


async def network_info(
    include_routes: bool = False,
    include_dns: bool = False,
    host: str = "local",
) -> str:
    """Get network interface information including IP addresses, MAC addresses, and link state.

    Args:
        include_routes: Also include the routing table.
        include_dns: Also include DNS resolver configuration.
        host: Target host name (default "local"). Use a configured host name to query a remote machine.

    Returns a JSON object with interfaces, and optionally routes and dns fields.
    """
    backend = get_registry().get(host)
    os_type = _get_os_type(backend, host)
    info: dict = {}

    # Network interfaces
    if os_type == "Darwin":
        result = await backend.run(["ifconfig"])
    else:
        result = await backend.run(["ip", "-brief", "addr"])

    if result.returncode == 0:
        info["interfaces"] = result.stdout.strip()

    # Routes
    if include_routes:
        if os_type == "Darwin":
            route_result = await backend.run(["netstat", "-rn"])
        else:
            route_result = await backend.run(["ip", "route"])
        if route_result.returncode == 0:
            info["routes"] = route_result.stdout.strip()

    # DNS
    if include_dns:
        dns_result = await backend.run(["cat", "/etc/resolv.conf"])
        if dns_result.returncode == 0:
            info["dns"] = dns_result.stdout.strip()

    return json.dumps(info, indent=2)
