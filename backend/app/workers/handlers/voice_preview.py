"""Amostra de uma voz (frase curta) para o usuario ouvir antes de escolher. Fica guardada e e reaproveitada."""
from __future__ import annotations

from ..errors import PermanentError

SAMPLE = ("No coração do espaço, existe um lugar onde a luz não consegue escapar. "
          "Poucos acreditariam no que os cientistas descobriram ali.")


def key_for(user_id: str, voice_id: str) -> str:
    return f"{user_id}/voices/{voice_id}.wav"


def run(task: dict, db, synth) -> dict:
    voice_id = task["payload"].get("voice_id")
    rows = db.select("voice_profiles", f"id=eq.{voice_id}&select=engine,model_ref,speed,style_prompt") if voice_id else []
    if not rows:
        raise PermanentError("voz nao encontrada")
    wav = synth(SAMPLE, rows[0])
    db.upload("media", key_for(task["user_id"], voice_id), wav, "audio/wav")
    return {"bytes": len(wav)}
