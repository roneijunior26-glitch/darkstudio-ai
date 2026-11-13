"""Exclui um projeto de verdade (arquivos, Release do GitHub, linhas) ou so libera espaco (imagens e audios)."""
from __future__ import annotations

from datetime import datetime, timezone

from ..errors import PermanentError


def all_keys(db, prefix: str) -> list[str]:
    keys = []
    for item in db.storage_list("media", prefix):
        path = f"{prefix}/{item['name']}"
        if item.get("id") is None:  # pasta
            keys += all_keys(db, path)
        else:
            keys.append(path)
    return keys


def run(task: dict, db, delete_release) -> dict:
    pid, uid, mode = task["payload"].get("project_id"), task["user_id"], task["payload"].get("mode", "delete")
    proj = db.select("projects", f"id=eq.{pid}&user_id=eq.{uid}&select=id") if pid else []
    if not proj:
        return {"skipped": "projeto nao existe mais"}
    keys = all_keys(db, f"{uid}/{pid}")
    if mode == "free_space":
        mid = [k for k in keys if "/images/" in k or "/audio/" in k]
        db.storage_remove("media", mid)
        db.update("media_assets", f"project_id=eq.{pid}&kind=in.(image,audio)", {"deleted_at": datetime.now(timezone.utc).isoformat()})
        return {"freed_files": len(mid)}
    if mode != "delete":
        raise PermanentError(f"modo desconhecido: {mode}")
    releases = 0
    for a in db.select("media_assets", f"project_id=eq.{pid}&kind=eq.export&select=storage_key"):
        key = a.get("storage_key") or ""
        if key.startswith("release:") and delete_release(key[len("release:"):]):
            releases += 1
    db.storage_remove("media", keys)
    db.delete("projects", f"id=eq.{pid}")  # cascata: cenas, tarefas, assets, exports, textos
    return {"files": len(keys), "releases": releases}
