"""Gera a imagem de uma cena com FLUX, guarda no Storage e registra o asset."""
from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone

from ...providers.base import CostTier, UsageEstimate
from ...providers.cost_guard import Decision, check
from ..errors import PermanentError, WaitQuota

STYLE_SUFFIX = ", dark moody cinematic, subject centered in frame, good contrast, sharp focus, intricate fine details, crisp textures, wide cinematic composition, no text, no watermark"


def daily_limit() -> float:
    return float(os.environ.get("FLUX_DAILY_LIMIT", "150"))  # conservador: ~170 imagens/dia medidas por terceiros


def run(task: dict, db, flux, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    scene_id = task["payload"]["scene_id"]
    rows = db.select("scenes", f"id=eq.{scene_id}&select=id,project_id,user_id,image_prompt,image_asset_id")
    if not rows:
        raise PermanentError("cena nao encontrada")
    scene = rows[0]
    if scene["image_asset_id"]:
        return {"skipped": "imagem ja existe"}
    if not scene["image_prompt"]:
        raise PermanentError("cena sem image_prompt")

    midnight = now.astimezone(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")  # sem "+": o servidor leria como espaco
    used = db.count("tasks", f"type=eq.generate_image&status=eq.COMPLETED&updated_at=gte.{midnight}")
    guard = check(tier=CostTier.FREE, authorized=True, estimate=UsageEstimate("image", 1), used_today=used,
                  daily_limit=None, conservative_limit=daily_limit(), now=now)
    if guard.decision is Decision.WAIT_QUOTA:
        raise WaitQuota(guard.retry_after, guard.reason)
    if guard.decision is not Decision.ALLOW:
        raise PermanentError(guard.reason)

    img = flux(scene["image_prompt"] + STYLE_SUFFIX)
    ext, ctype = ("png", "image/png") if img[:4] == b"\x89PNG" else ("jpg", "image/jpeg")
    key = f"{scene['user_id']}/{scene['project_id']}/images/{scene_id}.{ext}"
    db.upload("media", key, img, ctype)
    asset = db.insert("media_assets", [{
        "user_id": scene["user_id"], "project_id": scene["project_id"], "scene_id": scene_id, "kind": "image",
        "storage_backend": "supabase", "storage_key": key, "bytes": len(img), "sha256": hashlib.sha256(img).hexdigest(),
        "provider": "cloudflare-flux-1-schnell", "license": "Cloudflare Workers AI / FLUX.1 schnell (Apache-2.0)",
        "is_intermediate": True}])[0]
    db.update("scenes", f"id=eq.{scene_id}", {"image_asset_id": asset["id"], "status": "generating"})
    return {"asset_id": asset["id"], "bytes": len(img)}
