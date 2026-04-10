# Host Enrollment Design

## Context

Squire manages remote hosts via SSH, but adding a host currently requires manually configuring SSH keys, editing `squire.toml`, and restarting the application. This creates friction for users and exposes SSH configuration details that Squire should handle internally.

This feature replaces TOML-based host configuration with a managed enrollment flow. Squire generates dedicated SSH keys per host, attempts automatic key deployment using existing SSH access, and falls back to manual key copy. Hosts are persisted in the database and become available immediately without restart.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Bootstrap auth | Existing SSH keys/agent, then manual fallback | No password handling. Users either have SSH access or copy a key. |
| Password support | None | Avoids password transit entirely. Industry standard for security-conscious tools. |
| Persistence | SQLite database (replacing TOML `[[hosts]]`) | Enables hot-reload, CLI/web CRUD. Clean break from TOML. |
| TOML migration | Clean break | Users re-add hosts via CLI/web. Simplest code path. |
| Key storage | Flat directory: `~/.config/squire/keys/{name}` | Simple, one key pair per host. No metadata files (YAGNI). |
| Interfaces | CLI + Web UI | Chat agent delegates to the same backend naturally. |
| Host removal | Local cleanup only | Delete key + DB row. Orphaned public key on remote is harmless. |
| Key rotation | Deferred | Ships with enrollment; rotation uses the same deploy mechanism later. |

## Architecture

### New Modules

- **`src/squire/system/keys.py`** -- Ed25519 key generation and deletion via asyncssh.
- **`src/squire/hosts/store.py`** -- `HostStore` service: single entry point for enrollment, removal, verification, and DB-to-registry coordination.
- **`src/squire/hosts/__init__.py`** -- Package init.

### Modified Modules

- **`src/squire/database/service.py`** -- New `managed_hosts` table and CRUD methods.
- **`src/squire/system/registry.py`** -- Add `add_host()` and `remove_host()` for runtime mutations.
- **`src/squire/cli.py`** -- New `hosts` subcommand group (`add`, `remove`, `list`, `verify`).
- **`src/squire/api/routers/hosts.py`** -- Extend from read-only to full CRUD with enrollment endpoints.
- **`src/squire/api/schemas.py`** -- New request/response models.
- **`src/squire/api/app.py`** -- Wire `HostStore` into lifespan startup.
- **`src/squire/api/dependencies.py`** -- Add `host_store` singleton.
- **`src/squire/main.py`** — snapshot helpers shared by API, watch, and CLI (host loading happens in each entry path).
- **`web/src/app/hosts/page.tsx`** -- Add enrollment form, verify button, status badges.
- **`web/src/lib/types.ts`** -- New TypeScript types for enrollment.

### Removed

- TOML `[[hosts]]` loading from config loader (`config/loader.py` and any references).
- The `HostConfig` Pydantic model stays in `config/hosts.py` (used by HostStore and registry).

## Key Management (`system/keys.py`)

Storage location: `~/.config/squire/keys/`

```
~/.config/squire/keys/
  media-server        # private key (ed25519, 0600)
  media-server.pub    # public key (0644)
  prod-apps-01
  prod-apps-01.pub
```

Functions:

- `generate_key(name: str) -> tuple[Path, str]` -- Generate ed25519 key pair via `asyncssh.generate_private_key()`. Write private key (mode 0600) and public key (mode 0644) to the keys directory. Return `(private_key_path, public_key_text)`. Raise `FileExistsError` if key already exists for this host name.
- `get_key_path(name: str) -> Path | None` -- Return the private key path if it exists, else None.
- `get_public_key(name: str) -> str | None` -- Read and return the public key text if it exists.
- `delete_key(name: str) -> bool` -- Remove both key files. Return True if files existed.

The keys directory is created on first use with mode 0700.

## Database Schema

New table added to `DatabaseService._ensure_schema()`:

```sql
CREATE TABLE IF NOT EXISTS managed_hosts (
    name         TEXT PRIMARY KEY,
    address      TEXT NOT NULL,
    user         TEXT NOT NULL DEFAULT 'root',
    port         INTEGER NOT NULL DEFAULT 22,
    key_file     TEXT NOT NULL,
    tags         TEXT NOT NULL DEFAULT '[]',
    services     TEXT NOT NULL DEFAULT '[]',
    service_root TEXT NOT NULL DEFAULT '/opt',
    status       TEXT NOT NULL DEFAULT 'active',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
)
```

- `tags` and `services` are JSON-encoded arrays (consistent with `raw_json` pattern in snapshots).
- `status` is `'active'` (key deployed, connection verified) or `'pending_key'` (awaiting manual key installation).
- `key_file` stores the absolute path to the managed private key.

New `DatabaseService` methods:

- `save_managed_host(**fields) -> None` -- Insert or replace.
- `list_managed_hosts() -> list[dict]` -- All managed hosts.
- `get_managed_host(name: str) -> dict | None` -- Single host by name.
- `delete_managed_host(name: str) -> bool` -- Delete by name, return True if deleted.
- `update_managed_host_status(name: str, status: str) -> bool` -- Update status field.

## HostStore (`hosts/store.py`)

Central service for all host operations. Owns the relationship between the database, key management, and backend registry.

```python
class HostStore:
    def __init__(self, db: DatabaseService, registry: BackendRegistry) -> None: ...

    async def load(self) -> None:
        """Load all active managed hosts into the registry. Called at startup."""

    async def enroll(
        self,
        name: str,
        address: str,
        user: str = "root",
        port: int = 22,
        tags: list[str] | None = None,
        services: list[str] | None = None,
        service_root: str = "/opt",
    ) -> EnrollmentResult:
        """Full enrollment flow: generate key, attempt deploy, persist, register."""

    async def remove(self, name: str) -> None:
        """Remove a managed host: delete key, DB row, and registry entry."""

    async def verify(self, name: str) -> bool:
        """Test connectivity using the managed key. Update status on success."""

    async def list_hosts(self) -> list[HostConfig]:
        """All managed hosts from DB."""

    async def get_host(self, name: str) -> HostConfig | None:
        """Single host by name."""
```

### Enrollment Flow

`enroll()` step-by-step:

1. **Validate**: Check `name` is not already in the DB. Check `name != "local"`.
2. **Generate key**: Call `keys.generate_key(name)` -> `(key_path, public_key_text)`.
3. **Auto-deploy attempt**: Try `asyncssh.connect(address, port, username=user, known_hosts=None)` using the system's SSH agent and default keys (no explicit `client_keys`, no password). `known_hosts=None` is acceptable here because the user is explicitly trusting this host by enrolling it. If connected:
   - Capture the remote host key from the connection (`conn.get_extra_info('peer_host_key')`).
   - Add it to `~/.ssh/known_hosts` so future strict connections succeed.
   - Run `mkdir -p ~/.ssh && chmod 700 ~/.ssh` on the remote.
   - Append public key to `~/.ssh/authorized_keys` with a `# squire-managed:{name}` comment.
   - Run `chmod 600 ~/.ssh/authorized_keys` on the remote.
   - Close the ephemeral connection.
   - Test connection using the managed key (with strict host keys) to confirm it works.
   - Status: `active`.
4. **Manual fallback**: If auto-connect raises any exception:
   - Status: `pending_key`.
   - The `public_key_text` is returned to the caller for display.
5. **Persist**: Save host to DB with the resolved key path and status.
6. **Register**: Call `registry.add_host(config)` so the host is immediately available.
7. **Return**: `EnrollmentResult(name, status, public_key, message)`.

### EnrollmentResult

```python
class EnrollmentResult(BaseModel):
    name: str
    status: str          # "active" or "pending_key"
    public_key: str      # always included (for display in either case)
    message: str         # human-readable description of what happened
```

## Registry Changes (`system/registry.py`)

Add two methods to `BackendRegistry`:

```python
def add_host(self, config: HostConfig) -> None:
    """Register a new host at runtime."""
    self._hosts[config.name] = config
    self._backends.pop(config.name, None)  # evict any stale backend

async def remove_host(self, name: str) -> None:
    """Remove a host at runtime. Closes the backend if active."""
    self._hosts.pop(name, None)
    backend = self._backends.pop(name, None)
    if backend is not None:
        await backend.close()
```

The registry no longer receives TOML hosts at construction. Instead, `HostStore.load()` populates it at startup.

**Constructor change**: `BackendRegistry.__init__()` no longer accepts a `hosts` parameter (or accepts an empty list). The `HostStore` calls `add_host()` for each DB host during `load()`.

## CLI Commands (`cli.py`)

New `hosts` subcommand group following the existing `alerts` pattern:

### `squire hosts list`

Table output:
```
Name            Address       User   Port   Status       Tags
media-server    10.0.0.5      will   22     active       media, docker
prod-apps-01    10.20.0.100   svc    22     pending_key  production
```

### `squire hosts add`

```
squire hosts add \
  --name media-server \
  --address 10.0.0.5 \
  --user will \
  --port 22 \
  --tags media,docker \
  --services plex,sonarr \
  --service-root /opt
```

Output on auto-deploy success:
```
Generated SSH key for 'media-server'.
Deployed key to will@10.0.0.5 via existing SSH access.
Host 'media-server' enrolled successfully.
```

Output on manual fallback:
```
Generated SSH key for 'media-server'.
Could not connect to 10.0.0.5 with existing SSH credentials.

Add this public key to ~/.ssh/authorized_keys on the remote host:

  ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA... squire-managed:media-server

Then run: squire hosts verify media-server
```

### `squire hosts verify <name>`

Tests connection with the managed key:
```
Host 'media-server' is reachable. Status updated to active.
```
Or:
```
Could not connect to 'media-server' (10.0.0.5): Connection refused.
```

### `squire hosts remove <name>`

```
Host 'media-server' removed.
```

## API Endpoints

### New Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/hosts` | Enroll a new host |
| `DELETE` | `/api/hosts/{name}` | Remove a managed host |
| `POST` | `/api/hosts/{name}/verify` | Test/verify connectivity |
| `GET` | `/api/hosts/{name}/public-key` | Get public key text |

### Request/Response Schemas

```python
class HostCreate(BaseModel):
    name: str
    address: str
    user: str = "root"
    port: int = 22
    tags: list[str] = []
    services: list[str] = []
    service_root: str = "/opt"

class HostEnrollmentResponse(BaseModel):
    name: str
    status: str                  # "active" or "pending_key"
    public_key: str
    message: str

class HostVerifyResponse(BaseModel):
    name: str
    reachable: bool
    message: str
```

### Modified Endpoints

- `GET /api/hosts` -- Now sources from `HostStore` + local. Response includes `source` field (`"local"` or `"managed"`) and `status` field.
- `GET /api/hosts/{name}` -- Same change.

The `HostInfo` schema gains:
```python
source: str = "managed"   # "local" or "managed"
status: str = "active"    # "active" or "pending_key" (always "active" for local)
```

## Web UI Changes

### Host List (`web/src/app/hosts/page.tsx`)

- **Add Host button**: Opens a dialog (shadcn `Dialog` + `Form`) with fields: name, address, user (default "root"), port (default 22), tags (comma-separated input), services (comma-separated input).
- **Status badge**: Each host card shows `active` (green) or `pending_key` (amber) badge.
- **Pending hosts**: Show a "Verify" button on the card.

### Enrollment Result

After form submission:
- **Success**: Toast notification "Host enrolled successfully". Host appears in list.
- **Pending**: Dialog shows the public key in a copyable code block, with instructions and a "Verify" button.

### Host Detail

- **Remove button**: Confirmation dialog, then `DELETE /api/hosts/{name}`. Disabled for the `local` host.
- **Verify button**: Shown for `pending_key` hosts. Calls `POST /api/hosts/{name}/verify`.

### Types (`web/src/lib/types.ts`)

Add `source` and `status` fields to `HostInfo` type. Add `HostCreate`, `HostEnrollmentResponse`, `HostVerifyResponse` types.

## Startup Wiring

### `api/app.py` (web server lifespan)

```python
# Replace TOML host loading with HostStore
deps.registry = BackendRegistry()  # no hosts param
deps.host_store = HostStore(deps.db, deps.registry)
await deps.host_store.load()  # loads DB hosts into registry
tools_set_registry(deps.registry)
```

### `main.py` (snapshots / CLI helpers)

Same pattern: create empty registry, create HostStore, call `load()`.

### `api/dependencies.py`

Add `host_store: HostStore | None = None` and `get_host_store()` getter.

## Testing

### `tests/test_keys.py`

- Key generation writes correct files with correct permissions.
- Key generation raises `FileExistsError` on duplicate.
- `get_key_path` / `get_public_key` return None for nonexistent hosts.
- `delete_key` removes files and returns True / returns False for nonexistent.
- Uses `tmp_path` fixture with patched keys directory.

### `tests/test_host_store.py`

- **Enrollment (auto)**: Mock `asyncssh.connect` to succeed. Verify key generated, remote commands executed (mkdir, append, chmod), host saved to DB with `active` status, host added to registry.
- **Enrollment (manual fallback)**: Mock `asyncssh.connect` to raise. Verify host saved with `pending_key`, public key returned.
- **Verification**: Mock SSH connection with managed key. Verify status updated to `active`.
- **Removal**: Verify key deleted, DB row deleted, registry entry removed.
- **Duplicate name rejection**: Verify enrollment fails for existing name.
- **Load at startup**: Verify DB hosts are added to registry.

### `tests/test_registry.py` (extend existing)

- `add_host()` makes host available via `get()` and `host_names`.
- `remove_host()` removes host and closes backend.
- Adding a host evicts any stale cached backend.

### `tests/test_api_hosts.py`

- `POST /api/hosts` with valid body returns enrollment response.
- `DELETE /api/hosts/{name}` removes host.
- `POST /api/hosts/{name}/verify` returns verify response.
- `DELETE /api/hosts/local` returns 400 error.
- All tests mock `HostStore` methods.

## Verification

End-to-end testing after implementation:

1. **CLI enrollment (auto)**: From a machine with existing SSH access to a remote host, run `squire hosts add`. Verify the host appears in `squire hosts list` with `active` status and that tools work against it.
2. **CLI enrollment (manual)**: Run `squire hosts add` for a host without existing access. Verify public key is displayed. Copy key to remote host. Run `squire hosts verify`. Verify status becomes `active`.
3. **Web enrollment**: Start `squire web`. Open hosts page. Click "Add Host". Fill form. Verify enrollment result. Verify host appears in list.
4. **Host removal**: Run `squire hosts remove` or use the web UI. Verify host disappears from all interfaces.
5. **Restart persistence**: Add a host, restart Squire, verify it's still there and active.
6. **Run tests**: `uv run pytest` -- all existing + new tests pass.
7. **Run lint**: `uv run ruff check` + `uv run ruff format --check`.
