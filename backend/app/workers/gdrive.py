"""Envio do MP4 para o Google Drive do usuario (upload resumivel, somente stdlib).

Escopo recomendado: drive.file (o app so enxerga o que ele mesmo criou). Segredos via ambiente:
GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN (e opcional GOOGLE_DRIVE_FOLDER_NAME).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3"
CHUNK = 8 * 1024 * 1024  # multiplo de 256 KiB, exigido pelo Drive


class DriveError(RuntimeError):
    pass


def configured() -> bool:
    return all(os.environ.get(k) for k in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN"))


def _json(req: urllib.request.Request, timeout=120):
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raise DriveError(f"Drive HTTP {e.code}: {e.read()[:300].decode('utf-8', 'replace')}") from None


def access_token() -> str:
    body = urllib.parse.urlencode({"client_id": os.environ["GOOGLE_CLIENT_ID"], "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
                                   "refresh_token": os.environ["GOOGLE_REFRESH_TOKEN"], "grant_type": "refresh_token"}).encode()
    data = _json(urllib.request.Request(TOKEN_URL, data=body, method="POST"))
    if "access_token" not in data:
        raise DriveError("Drive: sem access_token (refresh token expirou ou foi revogado?)")
    return data["access_token"]


def _auth(tok: str, extra: dict | None = None) -> dict:
    return {"Authorization": f"Bearer {tok}", **(extra or {})}


def ensure_folder(tok: str, name: str) -> str:
    q = urllib.parse.quote(f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false")
    found = _json(urllib.request.Request(f"{API}/files?q={q}&fields=files(id)&spaces=drive", headers=_auth(tok)))
    if found.get("files"):
        return found["files"][0]["id"]
    made = _json(urllib.request.Request(f"{API}/files?fields=id", method="POST",
                                        data=json.dumps({"name": name, "mimeType": "application/vnd.google-apps.folder"}).encode(),
                                        headers=_auth(tok, {"Content-Type": "application/json"})))
    return made["id"]


def upload(path: Path, name: str, folder_name: str | None = None) -> dict:
    """Envia o arquivo e devolve {id, link, bytes}."""
    tok = access_token()
    folder = ensure_folder(tok, folder_name or os.environ.get("GOOGLE_DRIVE_FOLDER_NAME", "DarkStudio"))
    size = path.stat().st_size
    init = urllib.request.Request(
        f"{UPLOAD}/files?uploadType=resumable&fields=id,webViewLink,size", method="POST",
        data=json.dumps({"name": name, "parents": [folder]}).encode(),
        headers=_auth(tok, {"Content-Type": "application/json; charset=UTF-8", "X-Upload-Content-Type": "video/mp4",
                            "X-Upload-Content-Length": str(size)}))
    try:
        with urllib.request.urlopen(init, timeout=120) as r:
            session = r.headers["Location"]
    except urllib.error.HTTPError as e:
        raise DriveError(f"Drive HTTP {e.code} ao iniciar upload: {e.read()[:300].decode('utf-8', 'replace')}") from None
    sent = 0
    with open(path, "rb") as f:
        while True:
            chunk = f.read(CHUNK)
            if not chunk and size:
                raise DriveError("Drive: upload terminou sem confirmacao")
            end = sent + len(chunk) - 1
            req = urllib.request.Request(session, data=chunk, method="PUT", headers={
                "Content-Length": str(len(chunk)), "Content-Range": f"bytes {sent}-{end}/{size}" if size else "bytes */0"})
            try:
                with urllib.request.urlopen(req, timeout=300) as r:
                    info = json.loads(r.read() or b"{}")
                    return {"id": info["id"], "link": info.get("webViewLink"), "bytes": int(info.get("size", size))}
            except urllib.error.HTTPError as e:
                if e.code != 308:  # 308 = "continue enviando"
                    raise DriveError(f"Drive HTTP {e.code} no upload: {e.read()[:300].decode('utf-8', 'replace')}") from None
            sent += len(chunk)
