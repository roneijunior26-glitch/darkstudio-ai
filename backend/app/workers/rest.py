"""Cliente minimo do PostgREST do Supabase (somente stdlib). Usa a chave service_role do ambiente."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


class RestError(RuntimeError):
    pass


class Rest:
    def __init__(self, url: str | None = None, key: str | None = None):
        self.url = (url or os.environ["SUPABASE_URL"]).rstrip("/")
        self.key = key or os.environ["SUPABASE_SERVICE_KEY"]

    def _call(self, method: str, path: str, body=None, prefer: str | None = None):
        headers = {"apikey": self.key, "Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
        if prefer:
            headers["Prefer"] = prefer
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"{self.url}/rest/v1/{path}", data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            raise RestError(f"{method} {path.split('?')[0]} -> HTTP {e.code}: {e.read()[:300].decode('utf-8', 'replace')}") from None
        return json.loads(raw) if raw else None

    def select(self, table: str, query: str = ""):
        return self._call("GET", f"{table}?{query}")

    def insert(self, table: str, rows):
        return self._call("POST", table, rows, prefer="return=representation")

    def update(self, table: str, query: str, values: dict):
        return self._call("PATCH", f"{table}?{query}", values, prefer="return=representation")

    def delete(self, table: str, query: str):
        return self._call("DELETE", f"{table}?{query}")

    def count(self, table: str, query: str = "") -> int:
        headers = {"apikey": self.key, "Authorization": f"Bearer {self.key}", "Prefer": "count=exact", "Range": "0-0"}
        req = urllib.request.Request(f"{self.url}/rest/v1/{table}?{query}&select=id", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                total = r.headers.get("Content-Range", "*/0").split("/")[-1]
        except urllib.error.HTTPError as e:
            raise RestError(f"count {table} -> HTTP {e.code}") from None
        return int(total) if total.isdigit() else 0

    def upload(self, bucket: str, path: str, data: bytes, content_type: str):
        req = urllib.request.Request(f"{self.url}/storage/v1/object/{bucket}/{path}", data=data, method="POST",
                                     headers={"apikey": self.key, "Authorization": f"Bearer {self.key}",
                                              "Content-Type": content_type, "x-upsert": "true"})
        try:
            urllib.request.urlopen(req, timeout=120).read()
        except urllib.error.HTTPError as e:
            raise RestError(f"upload {bucket}/{path} -> HTTP {e.code}: {e.read()[:200].decode('utf-8', 'replace')}") from None

    def rpc(self, fn: str, args: dict | None = None):
        return self._call("POST", f"rpc/{fn}", args or {})
