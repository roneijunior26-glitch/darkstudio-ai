"""Renderiza o video final do projeto a partir das imagens e narracoes ja geradas."""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from .. import render
from ..errors import PermanentError


def run(task: dict, db, download, outdir: str | None = None, clip_fn=None) -> dict:
    pid = task["project_id"]
    if not render.have_ffmpeg():
        raise PermanentError("ffmpeg nao instalado no worker")
    scenes = db.select("scenes", f"project_id=eq.{pid}&deleted_at=is.null&order=position"
                                 "&select=id,position,narration_text,camera_move,transition,duration_s,"
                                 "image:media_assets!image_asset_id(storage_key),audio:media_assets!audio_asset_id(storage_key)")
    if not scenes:
        raise PermanentError("projeto sem cenas")
    missing = [s["position"] for s in scenes if not s.get("image") or not s.get("audio") or not s.get("duration_s")]
    if missing:
        raise RuntimeError(f"cenas sem imagem/narracao: {missing[:10]} (tenta de novo)")  # retry: assets ainda chegando

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
        target = out_dir / f"{pid}.mp4"
        shutil.move(str(final), target)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    db.update("projects", f"id=eq.{pid}", {"status": "awaiting_approval"})
    return {"file": target.name, "bytes": target.stat().st_size, "duration_s": round(total, 1), "scenes": len(scenes)}
