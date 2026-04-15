"""Supabase REST API wrapper that provides a DB-like interface for PaperTrader.

Uses Supabase's PostgREST API via httpx. No psycopg2 needed — works on Vercel.
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class SupabaseRow(dict):
    """Dict subclass that supports both row["key"] and row[index] access."""

    def __getitem__(self, key):
        if isinstance(key, str):
            return super().__getitem__(key)
        return list(self.values())[key]


class SupabaseDB:
    """Minimal DB interface backed by Supabase REST API.

    Provides table-level CRUD that PaperTrader can use instead of raw SQL.
    """

    def __init__(self, url: str, key: str):
        self.base_url = url.rstrip("/")
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        self._client = httpx.Client(
            base_url=f"{self.base_url}/rest/v1",
            headers=self.headers,
            timeout=15.0,
        )

    def select(
        self, table: str, *, where: dict | None = None, order: str | None = None, limit: int | None = None
    ) -> list[SupabaseRow]:
        params: dict[str, str] = {}
        if where:
            for k, v in where.items():
                if isinstance(v, (int, float)):
                    params[k] = f"eq.{v}"
                elif isinstance(v, str) and v.startswith(("gt.", "lt.", "gte.", "lte.", "eq.", "neq.")):
                    params[k] = v
                else:
                    params[k] = f"eq.{v}"
        if order:
            params["order"] = order
        if limit:
            params["limit"] = str(limit)

        resp = self._client.get(f"/{table}", params=params)
        resp.raise_for_status()
        return [SupabaseRow(row) for row in resp.json()]

    def select_one(self, table: str, *, where: dict) -> SupabaseRow | None:
        rows = self.select(table, where=where, limit=1)
        return rows[0] if rows else None

    def insert(self, table: str, data: dict | list[dict], *, upsert: bool = False) -> list[SupabaseRow]:
        headers = dict(self.headers)
        if upsert:
            headers["Prefer"] = "return=representation,resolution=merge-duplicates"

        resp = self._client.post(
            f"/{table}",
            json=data if isinstance(data, list) else [data],
            headers=headers,
        )
        resp.raise_for_status()
        return [SupabaseRow(row) for row in resp.json()]

    def upsert(self, table: str, data: dict | list[dict]) -> list[SupabaseRow]:
        return self.insert(table, data, upsert=True)

    def update(self, table: str, data: dict, *, where: dict) -> list[SupabaseRow]:
        params: dict[str, str] = {}
        for k, v in where.items():
            if isinstance(v, (int, float)):
                params[k] = f"eq.{v}"
            else:
                params[k] = f"eq.{v}"

        resp = self._client.patch(f"/{table}", json=data, params=params)
        resp.raise_for_status()
        return [SupabaseRow(row) for row in resp.json()]

    def delete(self, table: str, *, where: dict) -> int:
        params: dict[str, str] = {}
        if where:
            for k, v in where.items():
                params[k] = f"eq.{v}"

        resp = self._client.delete(f"/{table}", params=params)
        resp.raise_for_status()
        try:
            return len(resp.json())
        except Exception:
            return 0

    def delete_all(self, table: str, *, pk_column: str = "id") -> int:
        """Delete all rows. PostgREST needs a filter, so we use pk != impossible value."""
        params = {pk_column: "neq.___NONE___"}
        resp = self._client.delete(f"/{table}", params=params)
        resp.raise_for_status()
        try:
            return len(resp.json())
        except Exception:
            return 0

    def rpc(self, function_name: str, params: dict | None = None) -> Any:
        """Call a Postgres function via RPC."""
        resp = self._client.post(f"/rpc/{function_name}", json=params or {})
        resp.raise_for_status()
        return resp.json()

    def raw_sql(self, query: str) -> list[SupabaseRow]:
        """Execute raw SQL via Supabase's /rpc endpoint (requires a wrapper function)."""
        # Note: raw SQL is not directly available via PostgREST.
        # For aggregate queries, we use select + client-side computation.
        raise NotImplementedError("Use select/insert/update/delete methods instead")

    def close(self):
        self._client.close()
