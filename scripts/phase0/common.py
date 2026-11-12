"""Utilitarios da Fase 0 (somente stdlib). Nunca grava segredos em disco."""
from __future__ import annotations

import json
import os
import pathlib
import time
import urllib.error
import urllib.request

OUT = pathlib.Path(os.environ.get("PHASE0_OUT", "results"))
SECRET_ENVS = ("GEMINI_API_KEY", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID")


def redact(text: str) -> str:
    """Remove do texto o valor de qualquer segredo conhecido do ambiente."""
    for name in SECRET_ENVS:
        val = os.environ.get(name, "")
        if len(val) >= 6:
            text = text.replace(val, f"<{name}>")
    return text


def save(name: str, data: object, md: str | None = None) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.json").write_text(redact(json.dumps(data, indent=2, ensure_ascii=False, default=str)))
    if md is not None:
        (OUT / f"{name}.md").write_text(redact(md))


def request(url: str, *, method="GET", headers=None, body=None, timeout=120):
    """Retorna (status, headers, bytes, segundos). Nao levanta em HTTP 4xx/5xx."""
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read(), time.monotonic() - t0
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read(), time.monotonic() - t0
    except Exception as e:  # rede/timeout
        return 0, {}, str(e).encode(), time.monotonic() - t0


def skip(name: str, reason: str) -> None:
    print(f"[{name}] pulado: {reason}")
    save(name, {"status": "skipped", "reason": reason}, f"# {name}\n\nPulado: {reason}\n")
