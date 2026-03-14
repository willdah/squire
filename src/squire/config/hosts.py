"""Host configuration for multi-machine management.

Loaded from [[hosts]] array-of-tables in squire.toml.
"""

from pydantic import BaseModel, Field


class HostConfig(BaseModel):
    """Connection details for a single remote host."""

    name: str = Field(description="Unique alias for this host (e.g. 'media-server')")
    address: str = Field(description="Hostname or IP address")
    user: str = Field(default="root", description="SSH username")
    port: int = Field(default=22, description="SSH port")
    key_file: str | None = Field(default=None, description="Path to SSH private key (uses ssh-agent if omitted)")
    tags: list[str] = Field(default_factory=list, description="Optional tags for grouping (e.g. ['media', 'docker'])")
    services: list[str] = Field(
        default_factory=list,
        description="Docker Compose services on this host (e.g. ['syncthing', 'ollama'])",
    )
    service_root: str = Field(default="/opt", description="Root directory for compose service directories")
