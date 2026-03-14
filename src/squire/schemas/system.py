from datetime import datetime

from pydantic import BaseModel


class ContainerInfo(BaseModel):
    """Summary of a Docker container."""

    name: str
    image: str
    status: str
    state: str  # "running", "exited", "paused", etc.
    ports: str = ""


class DiskUsage(BaseModel):
    """Disk usage for a single mount point."""

    mount: str
    total_gb: float
    used_gb: float
    percent: float


class NetworkInterface(BaseModel):
    """Network interface information."""

    name: str
    ipv4: str | None = None
    ipv6: str | None = None
    mac: str | None = None
    state: str = "unknown"


class SystemSnapshot(BaseModel):
    """Point-in-time snapshot of system state."""

    timestamp: datetime
    hostname: str
    os_info: str = ""
    cpu_percent: float = 0.0
    memory_used_mb: float = 0.0
    memory_total_mb: float = 0.0
    disk_usage: list[DiskUsage] = []
    containers: list[ContainerInfo] = []
    network_interfaces: list[NetworkInterface] = []
    uptime_seconds: float = 0.0
