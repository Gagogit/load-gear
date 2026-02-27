"""File storage backends. Local filesystem for v0.1, GCS adapter later."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Protocol

from load_gear.core.config import get_config


class StorageBackend(Protocol):
    """Abstract file storage interface."""

    async def save(self, path: str, data: bytes) -> str:
        """Save data to storage. Returns the storage URI."""
        ...

    async def get(self, path: str) -> bytes:
        """Retrieve data from storage."""
        ...

    async def exists(self, path: str) -> bool:
        """Check if a file exists in storage."""
        ...


class LocalStorageBackend:
    """Stores files on the local filesystem under a configurable base path."""

    def __init__(self, base_path: Path) -> None:
        self.base_path = base_path
        self.base_path.mkdir(parents=True, exist_ok=True)

    async def save(self, path: str, data: bytes) -> str:
        """Save data to local filesystem. Returns the storage URI."""
        full_path = self.base_path / path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(data)
        return f"local://{path}"

    async def get(self, path: str) -> bytes:
        """Read file from local filesystem."""
        full_path = self.base_path / path
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        return full_path.read_bytes()

    async def exists(self, path: str) -> bool:
        """Check if file exists on local filesystem."""
        return (self.base_path / path).exists()


def compute_sha256(data: bytes) -> str:
    """Compute SHA-256 hex digest of file data."""
    return hashlib.sha256(data).hexdigest()


_storage: StorageBackend | None = None


def get_storage() -> StorageBackend:
    """Get the configured storage backend (singleton)."""
    global _storage
    if _storage is None:
        config = get_config()
        base_path = Path(config.storage.base_path)
        if not base_path.is_absolute():
            from load_gear.core.config import PROJECT_ROOT
            base_path = PROJECT_ROOT / base_path
        _storage = LocalStorageBackend(base_path)
    return _storage
