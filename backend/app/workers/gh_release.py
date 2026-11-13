"""Publica o MP4 como asset de um Release do proprio repositorio (ate 2 GB, sem prazo, download direto sem login).

Atencao: o repositorio e publico, entao o link do video e acessivel a quem souber a URL (a lista de Releases e publica).
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
import urllib.error
import urllib.request
import uuid
from pathlib import Path

API = "https://api.github.com"
UPLOADS = "https://uploads.github.com"


class ReleaseError(RuntimeError):
    pass


def configured() -> bool:
    return bool(os.environ.get("GITHUB_TOKEN") and os.environ.get("GITHUB_REPOSITORY"))


def ascii_name(title: str) -> str:
    s = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    return (re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")[:60] or "video") + ".mp4"


def _call(req: urllib.request.Request, timeout=120):
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raise ReleaseError(f"GitHub HTTP {e.code}: {e.read()[:300].decode('utf-8', 'replace')}") from None


def publish(path: Path, title: str) -> dict:
    """Cria o release e envia o arquivo. Devolve {tag, url (download direto), bytes}."""
    repo, token = os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"]
    hdr = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    tag = f"video-{uuid.uuid4().hex[:12]}"
    rel = _call(urllib.request.Request(f"{API}/repos/{repo}/releases", method="POST", headers={**hdr, "Content-Type": "application/json"},
                                       data=json.dumps({"tag_name": tag, "name": title[:120], "body": "Video gerado pelo DarkStudio AI.",
                                                        "draft": False, "prerelease": False}).encode()))
    name, size = ascii_name(title), path.stat().st_size
    with open(path, "rb") as f:
        asset = _call(urllib.request.Request(f"{UPLOADS}/repos/{repo}/releases/{rel['id']}/assets?name={name}", method="POST", data=f,
                                             headers={**hdr, "Content-Type": "video/mp4", "Content-Length": str(size)}), timeout=3600)
    return {"tag": tag, "url": asset["browser_download_url"], "bytes": size}


def delete(tag: str) -> bool:
    """Apaga o Release e a tag. False se ja nao existia."""
    repo, token = os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"]
    hdr = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    try:
        rel = _call(urllib.request.Request(f"{API}/repos/{repo}/releases/tags/{tag}", headers=hdr))
    except ReleaseError as e:
        if "HTTP 404" in str(e):
            return False
        raise
    _call(urllib.request.Request(f"{API}/repos/{repo}/releases/{rel['id']}", method="DELETE", headers=hdr))
    try:
        _call(urllib.request.Request(f"{API}/repos/{repo}/git/refs/tags/{tag}", method="DELETE", headers=hdr))
    except ReleaseError:
        pass  # a tag pode ja ter sumido junto com o release
    return True
