"""Host management endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_registry
from ..schemas import HostInfo, HostSnapshot

router = APIRouter()


@router.get("", response_model=list[HostInfo])
async def list_hosts(registry=Depends(get_registry)):
    """List all configured hosts with current status."""
    from ..app import get_latest_snapshot

    snapshot = await get_latest_snapshot()
    hosts = []
    for name in registry.host_names:
        cfg = registry.get_config(name)
        snap_data = snapshot.get(name)
        host = HostInfo(
            name=name,
            address=cfg.address if cfg else ("localhost" if name == "local" else ""),
            user=cfg.user if cfg else "",
            port=cfg.port if cfg else 22,
            tags=cfg.tags if cfg else [],
            services=cfg.services if cfg else [],
            snapshot=HostSnapshot(**snap_data) if snap_data else None,
        )
        hosts.append(host)
    return hosts


@router.get("/{name}", response_model=HostInfo)
async def host_detail(name: str, registry=Depends(get_registry)):
    """Host detail with config and latest snapshot."""
    from ..app import get_latest_snapshot

    if name not in registry.host_names:
        raise HTTPException(status_code=404, detail=f"Host '{name}' not found")

    snapshot = await get_latest_snapshot()
    cfg = registry.get_config(name)
    snap_data = snapshot.get(name)

    return HostInfo(
        name=name,
        address=cfg.address if cfg else ("localhost" if name == "local" else ""),
        user=cfg.user if cfg else "",
        port=cfg.port if cfg else 22,
        tags=cfg.tags if cfg else [],
        services=cfg.services if cfg else [],
        snapshot=HostSnapshot(**snap_data) if snap_data else None,
    )
