"""Video de ambiente (ex.: som de chuva por 1-10 h): 1 imagem fixa + trilha da biblioteca em loop."""
from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .. import cloudflare, render
from ..errors import PermanentError, WaitQuota
from .render_final import channel_logo_key, default_publish, safe_name

MAX_HOURS = 10.0
STYLE_SUFFIX = ", calm atmospheric, cinematic, soft lighting, wide 16:9 composition, no text, no watermark"


def hours_of(payload: dict) -> float:
    try:
        h = float(payload.get("hours"))
    except (TypeError, ValueError):
        raise PermanentError("duracao invalida") from None
    if not 0.05 <= h <= MAX_HOURS:
        raise PermanentError(f"duracao deve ficar entre 0,05 e {MAX_HOURS:g} horas")
    return h


def run(task: dict, db, download, flux, outdir: str | None = None, publish=None, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    pid, uid, pl = task["project_id"], task["user_id"], task.get("payload") or {}
    seconds = round(hours_of(pl) * 3600)
    if not render.have_ffmpeg():
        raise PermanentError("ffmpeg nao instalado no worker")
    proj = db.select("projects", f"id=eq.{pid}&select=title,channel_id")
    if not proj:
        raise PermanentError("projeto nao encontrado")
    title = safe_name(proj[0]["title"])
    track = db.select("music_assets", f"id=eq.{pl.get('track_id')}&select=name,storage_key") if pl.get("track_id") else []
    if not track or not track[0].get("storage_key"):
        raise PermanentError("faixa de audio nao encontrada na biblioteca")
    db.update("projects", f"id=eq.{pid}", {"status": "rendering"})

    img_key = pl.get("image_key")
    if img_key and not db.select("media_assets", f"project_id=eq.{pid}&storage_key=eq.{img_key}&select=id"):
        # imagem enviada pelo usuario: registra no projeto (o "Excluir" tambem apaga o arquivo)
        db.insert("media_assets", [{"user_id": uid, "project_id": pid, "kind": "image", "storage_backend": "supabase", "storage_key": img_key,
                                    "provider": "upload", "is_intermediate": True, "license": "imagem enviada pelo usuario"}])
    if not img_key:  # gera 1 imagem (reaproveita se uma tentativa anterior ja gerou)
        old = db.select("media_assets", f"project_id=eq.{pid}&kind=eq.image&order=created_at.desc&limit=1&select=storage_key")
        if old:
            img_key = old[0]["storage_key"]
        else:
            if not pl.get("image_prompt"):
                raise PermanentError("informe uma imagem ou uma descricao para gerar")
            try:
                img = flux(pl["image_prompt"] + STYLE_SUFFIX)
            except cloudflare.FluxQuota as e:
                raise WaitQuota(cloudflare.next_reset(now), f"cota diaria gratis da Cloudflare acabou; continua sozinho quando voltar ({str(e)[:160]})") from e
            ext, ctype = ("png", "image/png") if img[:4] == b"\x89PNG" else ("jpg", "image/jpeg")
            img_key = f"{uid}/{pid}/ambient.{ext}"
            db.upload("media", img_key, img, ctype)
            db.insert("media_assets", [{"user_id": uid, "project_id": pid, "kind": "image", "storage_backend": "supabase", "storage_key": img_key,
                                        "bytes": len(img), "provider": "cloudflare-flux-1-schnell", "is_intermediate": True,
                                        "license": "Cloudflare Workers AI / FLUX.1 schnell (Apache-2.0)"}])

    out_dir = Path(outdir or os.environ.get("OUTPUT_DIR", "out"))
    out_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="ambient-"))
    try:
        image = work / ("img" + (Path(img_key).suffix or ".jpg"))
        image.write_bytes(download("media", img_key))
        src = work / "src.audio"
        src.write_bytes(download("media", track[0]["storage_key"]))
        loop = work / "loop.wav"
        render.make_loop_unit(src, loop)
        src.unlink()
        logo = None
        lk = channel_logo_key(db, proj[0])
        if lk:
            try:
                logo = work / "logo.png"
                logo.write_bytes(download("media", lk))
            except Exception as e:  # noqa: BLE001  logo e extra
                print(f"[worker] sem logo ({e})", flush=True)
                logo = None
        final = work / "final.mp4"
        render.render_ambient(image, loop, seconds, final, logo)
        target = out_dir / f"{pid}.mp4"
        shutil.move(str(final), target)
        try:  # capa: imagem + titulo (best-effort)
            cap = work / "capa.jpg"
            render.make_thumbnail(image, title, cap)
            data = cap.read_bytes()
            key = f"{uid}/{pid}/thumbnail.jpg"
            db.upload("media", key, data, "image/jpeg")
            db.insert("media_assets", [{"user_id": uid, "project_id": pid, "kind": "thumbnail", "storage_backend": "supabase", "storage_key": key,
                                        "bytes": len(data), "provider": "ffmpeg", "is_intermediate": False, "license": "capa gerada a partir da imagem do video"}])
        except Exception as e:  # noqa: BLE001
            print(f"[worker] sem capa ({e})", flush=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    size = target.stat().st_size
    pub = (publish or default_publish)(target, f"{title}.mp4")
    asset = db.insert("media_assets", [{"user_id": uid, "project_id": pid, "kind": "export", "storage_backend": pub["backend"], "storage_key": pub["key"],
                                        "bytes": size, "origin_url": pub["url"], "is_intermediate": False, "license": "video gerado pelo usuario"}])[0]
    db.insert("project_exports", [{"user_id": uid, "project_id": pid, "asset_id": asset["id"], "kind": "mp4"}])
    db.update("projects", f"id=eq.{pid}", {"status": "awaiting_approval"})
    return {"file": target.name, "bytes": size, "duration_s": seconds, "stored_in": pub["backend"]}
