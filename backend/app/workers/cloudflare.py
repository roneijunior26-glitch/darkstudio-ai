"""FLUX-1-schnell via Cloudflare Workers AI (plano gratis: ~10.000 neurons/dia)."""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import json
import os
import urllib.error
import urllib.request


class FluxQuota(RuntimeError):
    pass


def next_reset(now: datetime | None = None) -> datetime:
    """Os 10.000 neurons gratis do Workers AI zeram a 00:00 UTC (21:00 em Brasilia); +5 min de folga."""
    now = now or datetime.now(timezone.utc)
    return now.replace(hour=0, minute=5, second=0, microsecond=0) + timedelta(days=1)


class FluxError(RuntimeError):
    pass


def generate(prompt: str, *, account: str | None = None, token: str | None = None) -> bytes:
    account = account or os.environ["CLOUDFLARE_ACCOUNT_ID"]
    token = token or os.environ["CLOUDFLARE_API_TOKEN"]
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/@cf/black-forest-labs/flux-1-schnell"
    req = urllib.request.Request(url, data=json.dumps({"prompt": prompt, "steps": int(os.environ.get("FLUX_STEPS", "4"))}).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        body = e.read()[:300].decode("utf-8", "replace")
        if e.code == 429:
            raise FluxQuota(f"HTTP 429: {body}") from None
        raise FluxError(f"HTTP {e.code}: {body}") from None
    try:
        b64 = (json.loads(raw).get("result") or {}).get("image")
        img = base64.b64decode(b64) if b64 else None
    except (ValueError, AttributeError):
        img = raw if raw[:2] == b"\xff\xd8" or raw[:4] == b"\x89PNG" else None
    if not img:
        raise FluxError("resposta sem imagem")
    return img
