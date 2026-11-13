"""Corta trechos do video pronto (Release do GitHub). Nao altera o original: cada corte vira um novo video."""
from __future__ import annotations

import shutil
import tempfile
import urllib.request
from pathlib import Path

from .. import gh_release, render
from ..errors import PermanentError

MAX_SEGMENTS, MAX_TOTAL_S = 20, 3600
VERTICAL = ("[0:v]split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=24:6[bg];"
            "[b]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p[v]")


def download_file(url: str, dest: Path) -> None:
    with urllib.request.urlopen(url, timeout=300) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f, 1 << 20)


def validate(segments) -> list[tuple[float, float]]:
    if not isinstance(segments, list) or not 1 <= len(segments) <= MAX_SEGMENTS:
        raise PermanentError(f"informe de 1 a {MAX_SEGMENTS} trechos")
    out = []
    for s in segments:
        try:
            a, b = float(s["in"]), float(s["out"])
        except (KeyError, TypeError, ValueError):
            raise PermanentError("trecho invalido") from None
        if not (0 <= a < b):
            raise PermanentError("cada trecho precisa ter inicio menor que o fim")
        out.append((a, b))
    if sum(b - a for a, b in out) > MAX_TOTAL_S:
        raise PermanentError("os trechos somam mais de 1 hora")
    return out


def cut_args(src: str, a: float, b: float, out: str, precise: bool, vertical: bool) -> list[str]:
    if not precise and not vertical:  # rapido: copia sem recodificar (corta no quadro-chave, ~1 s de precisao)
        return ["-ss", f"{a:.3f}", "-i", src, "-t", f"{b - a:.3f}", "-c", "copy", "-avoid_negative_ts", "make_zero", out]
    base = ["-ss", f"{a:.3f}", "-i", src, "-t", f"{b - a:.3f}"]
    enc = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out]
    if vertical:
        return base + ["-filter_complex", VERTICAL, "-map", "[v]", "-map", "0:a?"] + enc
    return base + enc


def run(task: dict, db, fetch=download_file, publish=gh_release.publish, ffmpeg=render.run_ffmpeg) -> dict:
    cut_id = task["payload"].get("cut_id")
    rows = db.select("video_cuts", f"id=eq.{cut_id}&user_id=eq.{task['user_id']}&select=id,project_id,export_id,segments,mode,name,vertical") if cut_id else []
    if not rows:
        raise PermanentError("corte nao encontrado")
    cut = rows[0]
    db.update("video_cuts", f"id=eq.{cut['id']}", {"status": "running", "error": None})
    try:
        segs = validate(cut["segments"])
        exp = db.select("project_exports", f"id=eq.{cut['export_id']}&select=asset_id")
        asset = db.select("media_assets", f"id=eq.{exp[0]['asset_id']}&select=origin_url") if exp else []
        url = (asset[0].get("origin_url") if asset else "") or ""
        if "/releases/download/" not in url:
            raise PermanentError("so da para cortar videos publicados com download direto (os mais antigos, so no artifact do GitHub, nao)")
        work = Path(tempfile.mkdtemp(prefix="cut-"))
        try:
            src = work / "source.mp4"
            fetch(url, src)
            precise, vertical = cut["mode"] == "precise", bool(cut.get("vertical"))
            parts = []
            for i, (a, b) in enumerate(segs):
                part = work / f"part{i:02d}.mp4"
                ffmpeg(cut_args(src.name, a, b, part.name, precise, vertical), cwd=work)
                parts.append(part)
            final = parts[0] if len(parts) == 1 else work / "final.mp4"
            if len(parts) > 1:
                render.concat(parts, final)
            title = (cut.get("name") or "corte").strip()[:80]
            pub = publish(final, title)
        finally:
            shutil.rmtree(work, ignore_errors=True)
        asset_row = db.insert("media_assets", [{
            "user_id": task["user_id"], "project_id": cut["project_id"], "kind": "export", "storage_backend": "github_artifact",
            "storage_key": f"release:{pub['tag']}", "bytes": pub["bytes"], "origin_url": pub["url"], "is_intermediate": False,
            "license": "corte do video gerado pelo usuario"}])[0]
        db.update("video_cuts", f"id=eq.{cut['id']}", {"status": "done", "output_asset_id": asset_row["id"], "error": None})
        return {"segments": len(segs), "bytes": pub["bytes"]}
    except PermanentError as e:
        db.update("video_cuts", f"id=eq.{cut['id']}", {"status": "failed", "error": str(e)[:300]})
        raise
    except Exception as e:  # noqa: BLE001 - falha tecnica: tarefa tenta de novo; o corte mostra o erro
        db.update("video_cuts", f"id=eq.{cut['id']}", {"status": "failed", "error": str(e)[:300]})
        raise
