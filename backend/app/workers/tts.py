"""Sintese de voz por cena. Motores: gemini (TTS do Gemini, plano gratis) e kokoro (local, Apache-2.0)."""
from __future__ import annotations

import base64
import io
import json
import os
import urllib.error
import urllib.request
import wave
from datetime import datetime, timedelta, timezone

from .errors import PermanentError, WaitQuota


def pcm_to_wav(pcm: bytes, rate: int = 24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def wav_duration(data: bytes) -> float:
    with wave.open(io.BytesIO(data)) as w:
        return w.getnframes() / w.getframerate()


def quota_wait(body: str, now: datetime) -> datetime:
    """429 por dia: espera ate 08:00 UTC (meia-noite do Pacifico, quando a cota do Google zera); por minuto: 90 s."""
    if "PerDay" in body or "per day" in body.lower():
        reset = now.replace(hour=8, minute=0, second=0, microsecond=0)
        return reset if reset > now else reset + timedelta(days=1)
    return now + timedelta(seconds=90)


def gemini_tts(text: str, model_ref: str, style_prompt: str | None, key: str | None = None, now: datetime | None = None) -> bytes:
    key = key or os.environ["GEMINI_API_KEY"]
    now = now or datetime.now(timezone.utc)
    model, _, voice = model_ref.partition(":")
    prompt = f"{style_prompt}: {text}" if style_prompt else text
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice or "Kore"}}}}}
    req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                                 data=json.dumps(body).encode(), method="POST",
                                 headers={"x-goog-api-key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        msg = e.read()[:600].decode("utf-8", "replace")
        if e.code == 429:
            raise WaitQuota(quota_wait(msg, now), "cota do Gemini TTS") from None
        if e.code in (500, 503):
            raise RuntimeError(f"Gemini TTS HTTP {e.code} (tenta de novo)") from None
        raise PermanentError(f"Gemini TTS HTTP {e.code}: {msg[:200]}") from None
    try:
        pcm = base64.b64decode(data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
    except (KeyError, IndexError, ValueError):
        raise RuntimeError("Gemini TTS sem audio na resposta (tenta de novo)") from None
    return pcm_to_wav(pcm, 24000)


_KOKORO = None
KOKORO_BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"


def kokoro_tts(text: str, voice: str, speed: float = 1.0) -> bytes:
    global _KOKORO
    import numpy as np  # importacao tardia: so quando a voz e Kokoro
    from kokoro_onnx import Kokoro

    if _KOKORO is None:
        d = os.environ.get("KOKORO_DIR", ".kokoro")
        os.makedirs(d, exist_ok=True)
        for f in ("kokoro-v1.0.onnx", "voices-v1.0.bin"):
            path = os.path.join(d, f)
            if not os.path.exists(path):
                urllib.request.urlretrieve(KOKORO_BASE + f, path)
        _KOKORO = Kokoro(os.path.join(d, "kokoro-v1.0.onnx"), os.path.join(d, "voices-v1.0.bin"))
    samples, rate = _KOKORO.create(text, voice=voice, speed=speed, lang="pt-br")
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()
    return pcm_to_wav(pcm, rate)


def synthesize(text: str, voice: dict) -> bytes:
    """`voice` = linha de voice_profiles."""
    engine = voice["engine"]
    if engine == "gemini":
        return gemini_tts(text, voice["model_ref"], voice.get("style_prompt"))
    if engine == "kokoro":
        return kokoro_tts(text, voice["model_ref"], float(voice.get("speed") or 1.0))
    raise PermanentError(f"motor de voz '{engine}' nao suportado no worker; escolha outra voz")
