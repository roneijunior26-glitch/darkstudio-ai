"""Renderiza o video final do projeto a partir das imagens e narracoes ja geradas."""
from __future__ import annotations

import os
import random
import re
import shutil
import tempfile
from pathlib import Path

from .. import gdrive, render
from ..errors import PermanentError


def safe_name(title: str) -> str:
    return re.sub(r"[^\w\- ]+", "", title).strip()[:80] or "video"


def pick_music(db, user_id: str, proj: dict):
    """Faixa escolhida no projeto; senao uma aleatoria da biblioteca; None se desligada/sem faixas."""
    if proj.get("music_enabled") is False:
        return None
    if proj.get("music_id"):
        rows = db.select("music_assets", f"id=eq.{proj['music_id']}&select=name,storage_key")
        if rows and rows[0].get("storage_key"):
            return rows[0]
    rows = [r for r in db.select("music_assets", f"user_id=eq.{user_id}&select=name,storage_key") if r.get("storage_key")]
    return random.choice(rows) if rows else None


def default_publish(path: Path, name: str) -> dict:
    """Drive se configurado; senao (ou se o Drive falhar) deixa o arquivo para o artifact do GitHub (7 dias)."""
    if gdrive.configured():
        try:
            info = gdrive.upload(path, name)
            path.unlink(missing_ok=True)  # ja esta no Drive: nao precisa subir como artifact
            return {"backend": "gdrive", "key": info["id"], "url": info["link"]}
        except gdrive.DriveError as e:
            print(f"[worker] Drive falhou, usando artifact do GitHub: {e}", flush=True)
    run_id, repo = os.environ.get("GITHUB_RUN_ID", ""), os.environ.get("GITHUB_REPOSITORY", "")
    return {"backend": "github_artifact", "key": f"video-{run_id}", "url": f"https://github.com/{repo}/actions/runs/{run_id}" if run_id else None}


def run(task: dict, db, download, outdir: str | None = None, clip_fn=None, publish=None) -> dict:
    pid = task["project_id"]
    scenes = db.select("scenes", f"project_id=eq.{pid}&deleted_at=is.null&order=position"
                                 "&select=id,position,narration_text,camera_move,transition,duration_s,"
                                 "image:media_assets!image_asset_id(storage_key),audio:media_assets!audio_asset_id(storage_key)")
    if not scenes:
        raise PermanentError("projeto sem cenas")
    missing = [s["position"] for s in scenes if not s.get("image") or not s.get("audio") or not s.get("duration_s")]
    if missing:
        raise RuntimeError(f"cenas sem imagem/narracao: {missing[:10]} (tenta de novo)")  # retry: assets ainda chegando

    if not render.have_ffmpeg():
        raise PermanentError("ffmpeg nao instalado no worker")
    proj = db.select("projects", f"id=eq.{pid}&select=title,music_enabled,music_id")
    title = safe_name(proj[0]["title"] if proj else pid)
    track = pick_music(db, task["user_id"], proj[0] if proj else {})
    db.update("projects", f"id=eq.{pid}", {"status": "rendering"})
    clip_fn = clip_fn or render.render_clip
    out_dir = Path(outdir or os.environ.get("OUTPUT_DIR", "out"))
    out_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="render-"))
    try:
        clips, total = [], 0.0
        for s in scenes:
            img = work / f"{s['position']:03d}{Path(s['image']['storage_key']).suffix or '.jpg'}"
            aud = work / f"{s['position']:03d}.wav"
            img.write_bytes(download("media", s["image"]["storage_key"]))
            aud.write_bytes(download("media", s["audio"]["storage_key"]))
            clip = work / f"{s['position']:03d}.mp4"
            total += clip_fn(img, aud, s, float(s["duration_s"]), clip)
            clips.append(clip)
            img.unlink(); aud.unlink()
        final = work / "final.mp4"
        render.concat(clips, final)
        if track:
            try:
                mus = work / "music.audio"
                mus.write_bytes(download("media", track["storage_key"]))
                mixed = work / "mixed.mp4"
                render.mix_music(final, mus, mixed, total)
                final = mixed
            except Exception as e:  # musica e extra: nunca derruba o video
                print(f"[worker] sem musica de fundo ({e})", flush=True)
        target = out_dir / f"{pid}.mp4"
        shutil.move(str(final), target)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    size = target.stat().st_size
    pub = (publish or default_publish)(target, f"{title}.mp4")
    asset = db.insert("media_assets", [{
        "user_id": task["user_id"], "project_id": pid, "kind": "export", "storage_backend": pub["backend"],
        "storage_key": pub["key"], "bytes": size, "origin_url": pub["url"], "is_intermediate": False,
        "license": "video gerado pelo usuario"}])[0]
    db.insert("project_exports", [{"user_id": task["user_id"], "project_id": pid, "asset_id": asset["id"], "kind": "mp4"}])
    db.update("projects", f"id=eq.{pid}", {"status": "awaiting_approval"})
    return {"file": target.name, "bytes": size, "duration_s": round(total, 1), "scenes": len(scenes), "stored_in": pub["backend"]}
