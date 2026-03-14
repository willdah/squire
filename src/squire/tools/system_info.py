"""system_info tool — OS, CPU, memory, disk, uptime."""

import json
import platform

from ..system import LocalBackend

RISK_LEVEL = "read"

_backend = LocalBackend()


async def system_info() -> str:
    """Get system information including OS, CPU usage, memory usage, disk usage, and uptime.

    Returns a JSON object with hostname, os, cpu_percent, memory, disk, and uptime fields.
    """
    info: dict = {
        "hostname": platform.node(),
        "os": f"{platform.system()} {platform.release()}",
        "architecture": platform.machine(),
    }

    # CPU usage (Linux: /proc/stat is complex, use top/vmstat; macOS: sysctl)
    if platform.system() == "Darwin":
        cpu_result = await _backend.run(
            ["sysctl", "-n", "hw.ncpu"],
        )
        info["cpu_cores"] = cpu_result.stdout.strip()

        # CPU usage via ps
        cpu_usage = await _backend.run(
            ["ps", "-A", "-o", "%cpu"],
        )
        try:
            values = [float(line.strip()) for line in cpu_usage.stdout.strip().split("\n")[1:] if line.strip()]
            info["cpu_percent"] = round(sum(values), 1)
        except (ValueError, IndexError):
            info["cpu_percent"] = -1
    else:
        # Linux: use nproc and /proc/stat or top
        cpu_result = await _backend.run(["nproc"])
        info["cpu_cores"] = cpu_result.stdout.strip()

        cpu_usage = await _backend.run(
            ["grep", "cpu ", "/proc/stat"],
        )
        try:
            fields = cpu_usage.stdout.strip().split()
            idle = int(fields[4])
            total = sum(int(f) for f in fields[1:])
            info["cpu_percent"] = round((1 - idle / total) * 100, 1) if total > 0 else -1
        except (ValueError, IndexError):
            info["cpu_percent"] = -1

    # Memory
    if platform.system() == "Darwin":
        mem_result = await _backend.run(["sysctl", "-n", "hw.memsize"])
        try:
            total_bytes = int(mem_result.stdout.strip())
            info["memory_total_mb"] = round(total_bytes / (1024 * 1024))
        except ValueError:
            info["memory_total_mb"] = -1

        vm_result = await _backend.run(["vm_stat"])
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
            info["memory_used_mb"] = -1
    else:
        mem_result = await _backend.run(["free", "-m"])
        try:
            lines = mem_result.stdout.strip().split("\n")
            parts = lines[1].split()
            info["memory_total_mb"] = int(parts[1])
            info["memory_used_mb"] = int(parts[2])
        except (ValueError, IndexError):
            info["memory_total_mb"] = -1
            info["memory_used_mb"] = -1

    # Disk usage
    df_result = await _backend.run(["df", "-h"])
    if df_result.returncode == 0:
        info["disk_usage"] = df_result.stdout.strip()

    # Uptime
    uptime_result = await _backend.run(["uptime"])
    if uptime_result.returncode == 0:
        info["uptime"] = uptime_result.stdout.strip()

    return json.dumps(info, indent=2)
