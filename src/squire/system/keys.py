"""SSH key management — generate, retrieve, and delete ed25519 key pairs.

Keys are stored in SQUIRE_KEYS_DIR (default ~/.config/squire/keys/) with one file per host:
  {name}       — private key (mode 0600)
  {name}.pub   — public key (mode 0644)
"""

from __future__ import annotations

import os
from pathlib import Path

import asyncssh


def _keys_dir() -> Path:
    """Return the keys storage directory.

    Reads SQUIRE_KEYS_DIR env var, falling back to ~/.config/squire/keys/.
    """
    if env := os.environ.get("SQUIRE_KEYS_DIR"):
        return Path(env)
    return Path.home() / ".config" / "squire" / "keys"


def generate_key(name: str) -> tuple[Path, str]:
    """Generate an ed25519 key pair for a host.

    Returns:
        Tuple of (private_key_path, public_key_text).

    Raises:
        FileExistsError: If a key already exists for this host name.
    """
    keys = _keys_dir()
    keys.mkdir(parents=True, exist_ok=True)
    os.chmod(keys, 0o700)

    private_path = keys / name
    pub_path = keys / f"{name}.pub"

    if private_path.exists():
        raise FileExistsError(f"Key already exists for host '{name}': {private_path}")

    key = asyncssh.generate_private_key("ssh-ed25519")
    comment = f"squire-managed:{name}"

    private_path.write_bytes(key.export_private_key())
    os.chmod(private_path, 0o600)

    public_text = key.export_public_key("openssh").decode().strip() + f" {comment}"
    pub_path.write_text(public_text + "\n")
    os.chmod(pub_path, 0o644)

    return private_path, public_text


def get_key_path(name: str) -> Path | None:
    """Return the private key path if it exists, else None."""
    path = _keys_dir() / name
    return path if path.exists() else None


def get_public_key(name: str) -> str | None:
    """Return the public key text if it exists, else None."""
    path = _keys_dir() / f"{name}.pub"
    if not path.exists():
        return None
    return path.read_text().strip()


def delete_key(name: str) -> bool:
    """Delete the key pair for a host. Returns True if files existed."""
    keys = _keys_dir()
    private_path = keys / name
    pub_path = keys / f"{name}.pub"
    existed = private_path.exists() or pub_path.exists()
    private_path.unlink(missing_ok=True)
    pub_path.unlink(missing_ok=True)
    return existed
