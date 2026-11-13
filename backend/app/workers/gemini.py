"""Chamada ao Gemini (plano gratis) para texto/JSON, com retry em 429/5xx."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

DEFAULT_MODEL = "gemini-3.5-flash-lite"  # configuravel: os nomes mudam com frequencia


class GeminiError(RuntimeError):
    pass


def generate_json(prompt: str, *, model: str | None = None, key: str | None = None, attempts: int = 4):
    model = model or os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    key = key or os.environ["GEMINI_API_KEY"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}],
                       "generationConfig": {"responseMimeType": "application/json", "temperature": 0.4}}).encode()
    last = ""
    for i in range(attempts):
        req = urllib.request.Request(url, data=body, headers={"x-goog-api-key": key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                data = json.loads(r.read())
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code not in (429, 500, 503):
                raise GeminiError(f"{last}: {e.read()[:200].decode('utf-8', 'replace')}") from None
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            last = f"resposta invalida ({type(e).__name__})"
        time.sleep(5 * (i + 1))
    raise GeminiError(f"Gemini indisponivel apos {attempts} tentativas: {last}")
