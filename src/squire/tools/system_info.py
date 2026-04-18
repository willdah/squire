"""system_info tool — OS, CPU, memory, disk, uptime."""

import json
import logging
import platform

from ._effects import Effect
from ._registry import get_registry

logger = logging.getLogger(__name__)

RISK_LEVEL = 1  # Info
EFFECT: Effect = "read"


def _get_os_type(backend, host: str) -> str:
    """Determine the OS type for the target host."""
    if host == "local":
        return platform.system()
    return getattr(backend, "os_type", "Linux")


async def system_info(host: str = "local") -> str:
    """Get system information including OS, CPU usage, memory usage, disk usage, and uptime.

    Args:
        host: Target host name (default "local"). Use a configured host name to query a remote machine.

    Returns a JSON object with hostname, os, cpu_percent, memory, disk, and uptime fields.
    """
    backend = get_registry().get(host)
    os_type = _get_os_type(backend, host)

    info: dict = {}

    # Hostname — use the backend for remote hosts
    if host == "local":
        info["hostname"] = platform.node()
        info["os"] = f"{platform.system()} {platform.release()}"
        info["architecture"] = platform.machine()
    else:
        hostname_result = await backend.run(["hostname"])
        info["hostname"] = hostname_result.stdout.strip() or host

        os_result = await backend.run(["uname", "-sr"])
        info["os"] = os_result.stdout.strip() or os_type

        arch_result = await backend.run(["uname", "-m"])
        info["architecture"] = arch_result.stdout.strip()

    # CPU usage
    if os_type == "Darwin":
        cpu_result = await backend.run(["sysctl", "-n", "hw.ncpu"])
        info["cpu_cores"] = cpu_result.stdout.strip()

        cpu_usage = await backend.run(["ps", "-A", "-o", "%cpu"])
        try:
            values = [float(line.strip()) for line in cpu_usage.stdout.strip().split("\n")[1:] if line.strip()]
            info["cpu_percent"] = round(sum(values), 1)
        except (ValueError, IndexError):
            logger.debug("failed to parse CPU usage on Darwin", exc_info=True)
            info["cpu_percent"] = -1
    else:
        cpu_result = await backend.run(["nproc"])
        info["cpu_cores"] = cpu_result.stdout.strip()

        cpu_usage = await backend.run(["grep", "cpu ", "/proc/stat"])
        try:
            fields = cpu_usage.stdout.strip().split()
            idle = int(fields[4])
            total = sum(int(f) for f in fields[1:])
            info["cpu_percent"] = round((1 - idle / total) * 100, 1) if total > 0 else -1
        except (ValueError, IndexError):
            logger.debug("failed to parse CPU usage from /proc/stat", exc_info=True)
            info["cpu_percent"] = -1

    # Memory
    if os_type == "Darwin":
        mem_result = await backend.run(["sysctl", "-n", "hw.memsize"])
        try:
            total_bytes = int(mem_result.stdout.strip())
            info["memory_total_mb"] = round(total_bytes / (1024 * 1024))
        except ValueError:
            logger.debug("failed to parse memory total on Darwin", exc_info=True)
            info["memory_total_mb"] = -1

        vm_result = await backend.run(["vm_stat"])
        try:
            lines = vm_result.stdout.strip().split("\n")
            page_size = 16384  # default on Apple Silicon
            for line in lines:
                if "page size of" in line:
                    page_size = int(line.split()[-2])
                    break
            free_pages = 0
            for line in lines:
                if "Pages free" in line:
                    free_pages = int(line.split()[-1].rstrip("."))
                    break
            free_mb = (free_pages * page_size) / (1024 * 1024)
            info["memory_used_mb"] = round(info.get("memory_total_mb", 0) - free_mb)
        except (ValueError, IndexError):
            logger.debug("failed to parse vm_stat output on Darwin", exc_info=True)
            info["memory_used_mb"] = -1
    else:
        mem_result = await backend.run(["free", "-m"])
        try:
            lines = mem_result.stdout.strip().split("\n")
            parts = lines[1].split()
            info["memory_total_mb"] = int(parts[1])
            info["memory_used_mb"] = int(parts[2])
        except (ValueError, IndexError):
            logger.debug("failed to parse 'free -m' output", exc_info=True)
            info["memory_total_mb"] = -1
            info["memory_used_mb"] = -1

    # Disk usage
    df_result = await backend.run(["df", "-h"])
    if df_result.returncode == 0:
        info["disk_usage"] = df_result.stdout.strip()

    # Uptime
    uptime_result = await backend.run(["uptime"])
    if uptime_result.returncode == 0:
        info["uptime"] = uptime_result.stdout.strip()

    return json.dumps(info, indent=2)
