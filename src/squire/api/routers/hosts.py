"""Host management endpoints — list, enroll, verify, remove."""

from fastapi import APIRouter, Depends, HTTPException

from ...system.keys import get_public_key
from ..dependencies import get_host_store, get_registry
from ..schemas import HostCreate, HostEnrollmentResponse, HostInfo, HostSnapshot, HostVerifyResponse

router = APIRouter()


@router.get("", response_model=list[HostInfo])
async def list_hosts(registry=Depends(get_registry), host_store=Depends(get_host_store)):
    """List all hosts (local + managed) with current status."""
    from ..app import get_latest_snapshot

    snapshot = await get_latest_snapshot()
    hosts = []

    # Local host
    snap_data = snapshot.get("local")
    hosts.append(
        HostInfo(
            name="local",
            address="localhost",
            source="local",
            status="active",
            snapshot=HostSnapshot(**snap_data) if snap_data else None,
        )
    )

    # Managed hosts from DB
    db_hosts = await host_store._db.list_managed_hosts()
    for row in db_hosts:
        cfg = host_store._row_to_config(row)
        snap_data = snapshot.get(cfg.name)
        hosts.append(
            HostInfo(
                name=cfg.name,
                address=cfg.address,
                user=cfg.user,
                port=cfg.port,
                tags=cfg.tags,
                services=cfg.services,
                source="managed",
                status=row["status"],
                snapshot=HostSnapshot(**snap_data) if snap_data else None,
            )
        )

    return hosts


@router.get("/{name}", response_model=HostInfo)
async def host_detail(name: str, registry=Depends(get_registry), host_store=Depends(get_host_store)):
    """Host detail with config and latest snapshot."""
    from ..app import get_latest_snapshot

    snapshot = await get_latest_snapshot()

    if name == "local":
        snap_data = snapshot.get("local")
        return HostInfo(
            name="local",
            address="localhost",
            source="local",
            status="active",
            snapshot=HostSnapshot(**snap_data) if snap_data else None,
        )

    host = await host_store.get_host(name)
    if host is None:
        raise HTTPException(status_code=404, detail=f"Host '{name}' not found")

    row = await host_store._db.get_managed_host(name)
    snap_data = snapshot.get(name)

    return HostInfo(
        name=host.name,
        address=host.address,
        user=host.user,
        port=host.port,
        tags=host.tags,
        services=host.services,
        source="managed",
        status=row["status"] if row else "active",
        snapshot=HostSnapshot(**snap_data) if snap_data else None,
    )


@router.post("", response_model=HostEnrollmentResponse, status_code=201)
async def enroll_host(body: HostCreate, host_store=Depends(get_host_store), registry=Depends(get_registry)):
    """Enroll a new managed host."""
    from ...main import _collect_snapshot
    from ..app import get_latest_snapshot, set_latest_snapshot

    try:
        result = await host_store.enroll(
            name=body.name,
            address=body.address,
            user=body.user,
            port=body.port,
            tags=body.tags,
            services=body.services,
            service_root=body.service_root,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Collect a snapshot for the new host so it appears connected immediately
    if result.status == "active":
        try:
            snap = await _collect_snapshot(host=body.name)
            current = await get_latest_snapshot()
            current[body.name] = snap
            await set_latest_snapshot(current)
        except Exception:
            pass  # non-fatal — snapshot will be collected on next background cycle

    return result


@router.delete("/{name}", status_code=204)
async def remove_host(name: str, host_store=Depends(get_host_store)):
    """Remove a managed host."""
    from ..app import get_latest_snapshot, set_latest_snapshot

    if name == "local":
        raise HTTPException(status_code=400, detail="Cannot remove the local host")
    try:
        await host_store.remove(name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Remove from snapshot cache
    current = await get_latest_snapshot()
    current.pop(name, None)
    await set_latest_snapshot(current)


@router.post("/{name}/verify", response_model=HostVerifyResponse)
async def verify_host(name: str, host_store=Depends(get_host_store)):
    """Verify connectivity to a managed host."""
    from ...main import _collect_snapshot
    from ..app import get_latest_snapshot, set_latest_snapshot

    try:
        reachable = await host_store.verify(name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if reachable:
        try:
            snap = await _collect_snapshot(host=name)
            current = await get_latest_snapshot()
            current[name] = snap
            await set_latest_snapshot(current)
        except Exception:
            pass

    return HostVerifyResponse(
        name=name,
        reachable=reachable,
        message="Host is reachable." if reachable else "Could not connect.",
    )


@router.get("/{name}/public-key")
async def get_host_public_key(name: str, host_store=Depends(get_host_store)):
    """Get the public key for a managed host."""
    host = await host_store.get_host(name)
    if host is None:
        raise HTTPException(status_code=404, detail=f"Host '{name}' not found")
    pub_key = get_public_key(name)
    if pub_key is None:
        raise HTTPException(status_code=404, detail=f"No public key found for host '{name}'")
    return {"name": name, "public_key": pub_key}
