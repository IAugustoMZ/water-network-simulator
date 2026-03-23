"""
In-memory stores for network graphs and simulation results.
Thread-safe via asyncio.Lock with TTL-based expiry.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional


class _BaseStore:
    """Generic async in-memory store with TTL expiry."""

    def __init__(self, ttl_hours: int = 2) -> None:
        self._store: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self.ttl = timedelta(hours=ttl_hours)

    async def put(
        self,
        obj: Any,
        metadata: Dict[str, Any],
        store_id: Optional[str] = None,
    ) -> str:
        """Store object, return its ID (generated UUID if not provided)."""
        sid = store_id or str(uuid.uuid4())
        async with self._lock:
            self._store[sid] = {
                "object": obj,
                "metadata": metadata,
                "created_at": datetime.utcnow(),
                **metadata,  # also expose metadata at top level for convenience
            }
        return sid

    async def get(self, store_id: str) -> Optional[Dict[str, Any]]:
        """Return the stored entry dict, or None if missing or expired."""
        async with self._lock:
            entry = self._store.get(store_id)
            if entry is None:
                return None
            age = datetime.utcnow() - entry["created_at"]
            if age > self.ttl:
                del self._store[store_id]
                return None
            return entry

    async def delete(self, store_id: str) -> bool:
        """Delete an entry. Returns True if it existed."""
        async with self._lock:
            return self._store.pop(store_id, None) is not None

    async def delete_expired(self) -> int:
        """Purge all expired entries. Returns count removed."""
        now = datetime.utcnow()
        async with self._lock:
            expired = [
                k for k, v in self._store.items()
                if (now - v["created_at"]) > self.ttl
            ]
            for k in expired:
                del self._store[k]
        return len(expired)

    async def list_ids(self) -> list[str]:
        """Return all currently stored (non-expired) IDs."""
        now = datetime.utcnow()
        async with self._lock:
            return [
                k for k, v in self._store.items()
                if (now - v["created_at"]) <= self.ttl
            ]


class NetworkStore(_BaseStore):
    """Store for NetworkGraph objects and their associated metadata."""

    def __init__(self) -> None:
        super().__init__(ttl_hours=4)   # networks live longer than results


class ResultStore(_BaseStore):
    """Store for SimulationResult objects."""

    def __init__(self) -> None:
        super().__init__(ttl_hours=2)


# Module-level singletons — import these throughout the application
network_store = NetworkStore()
result_store = ResultStore()
