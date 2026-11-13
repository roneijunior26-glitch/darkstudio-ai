"""Gera a narracao de uma cena com a voz do projeto e mede a duracao real."""
from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone

from ...providers.base import CostTier, UsageEstimate
from ...providers.cost_guard import Decision, check
from ..errors import PermanentError, WaitQuota
from ..tts import wav_duration


def daily_limit() -> float:
    return float(os.environ.get("TTS_DAILY_LIMIT", "100"))  # conservador: cota do Gemini TTS desconhecida


def pick_voice(db, project_id: str) -> dict:
    proj = db.select("projects", f"id=eq.{project_id}&select=voice_id,channel_id")[0]
    voice_id = proj.get("voice_id")
    if not voice_id:
        ch = db.select("channels", f"id=eq.{proj['channel_id']}&select=default_voice_id,niche_preset_id")[0]
        voice_id = ch.get("default_voice_id")
        if not voice_id and ch.get("niche_preset_id"):
            voice_id = db.select("niche_presets", f"id=eq.{ch['niche_preset_id']}&select=default_voice_id")[0].get("default_voice_id")
    if not voice_id:
        raise PermanentError("projeto sem voz: escolha uma voz no projeto, no canal ou no nicho")
    rows = db.select("voice_profiles", f"id=eq.{voice_id}&select=engine,model_ref,speed,style_prompt")
    if not rows:
        raise PermanentError("voz do projeto nao encontrada")
    return rows[0]


def run(task: dict, db, synth, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    scene_id = task["payload"]["scene_id"]
    rows = db.select("scenes", f"id=eq.{scene_id}&select=id,project_id,user_id,narration_text,audio_asset_id")
    if not rows:
        raise PermanentError("cena nao encontrada")
    scene = rows[0]
    if scene["audio_asset_id"]:
        return {"skipped": "narracao ja existe"}

    voice = pick_voice(db, scene["project_id"])
    if voice["engine"] == "gemini":  # so o Gemini tem cota; Kokoro e local
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        used = db.count("tasks", f"type=eq.generate_audio&status=eq.COMPLETED&updated_at=gte.{midnight}")
        guard = check(tier=CostTier.FREE, authorized=True, estimate=UsageEstimate("request", 1), used_today=used,
                      daily_limit=None, conservative_limit=daily_limit(), now=now)
        if guard.decision is Decision.WAIT_QUOTA:
            raise WaitQuota(guard.retry_after, guard.reason)

    wav = synth(scene["narration_text"], voice)
    dur = round(wav_duration(wav), 2)
    key = f"{scene['user_id']}/{scene['project_id']}/audio/{scene_id}.wav"
    db.upload("media", key, wav, "audio/wav")
    asset = db.insert("media_assets", [{
        "user_id": scene["user_id"], "project_id": scene["project_id"], "scene_id": scene_id, "kind": "audio",
        "storage_backend": "supabase", "storage_key": key, "bytes": len(wav), "sha256": hashlib.sha256(wav).hexdigest(),
        "provider": voice["engine"], "license": "voz sintetica (ver voice_profiles)", "is_intermediate": True}])[0]
    db.update("scenes", f"id=eq.{scene_id}", {"audio_asset_id": asset["id"], "duration_s": dur})
    return {"asset_id": asset["id"], "duration_s": dur}
