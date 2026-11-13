"""Alternativas de TTS pt-BR: Gemini TTS, Edge-TTS, Kokoro. Audios ficam so no artifact."""
import base64
import json
import os
import subprocess
import sys
import time
import urllib.request
import wave

from common import OUT, request, save

OUT.mkdir(parents=True, exist_ok=True)
TEXT = ("Em mil novecentos e oitenta e seis, um farol abandonado na costa da Noruega voltou a emitir luz. "
        "Ninguém sabia quem o acendera, e os pescadores evitavam falar do assunto. "
        "Dizem que, nas noites de nevoeiro, uma sombra ainda caminha pela galeria.")
res = {}


def wav_dur(p):
    with wave.open(str(p)) as w:
        return w.getnframes() / w.getframerate()


# 1) Gemini TTS
key = os.environ.get("GEMINI_API_KEY")
if key:
    for model in ("gemini-2.5-flash-preview-tts", "gemini-3.1-flash-tts-preview"):
        for voice in ("Kore", "Charon"):
            body = {"contents": [{"parts": [{"text": "Narre em português do Brasil, em tom grave e misterioso, de documentário: " + TEXT}]}],
                    "generationConfig": {"responseModalities": ["AUDIO"],
                                         "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
            st, _, raw, secs = request(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                method="POST", headers={"x-goog-api-key": key}, body=body, timeout=120)
            r = {"http": st, "sec": round(secs, 1)}
            if st == 200:
                try:
                    part = json.loads(raw)["candidates"][0]["content"]["parts"][0]["inlineData"]
                    pcm = base64.b64decode(part["data"])
                    out = OUT / f"gemini_{model}_{voice}.wav"
                    with wave.open(str(out), "wb") as w:
                        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(pcm)
                    r["audio_sec"] = round(wav_dur(out), 1)
                except Exception as e:
                    r["parse_error"] = str(e)
            else:
                r["error"] = raw[:300].decode("utf-8", "replace")
            res[f"gemini:{model}:{voice}"] = r
else:
    res["gemini"] = "sem chave"

# 2) Edge-TTS
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "edge-tts"], capture_output=True)
for voice in ("pt-BR-AntonioNeural", "pt-BR-FranciscaNeural", "pt-BR-ThalitaMultilingualNeural"):
    out = OUT / f"edge_{voice}.mp3"
    t0 = time.monotonic()
    p = subprocess.run([sys.executable, "-m", "edge_tts", "--voice", voice, "--text", TEXT, "--write-media", str(out)],
                       capture_output=True, text=True, timeout=120)
    res[f"edge:{voice}"] = {"rc": p.returncode, "sec": round(time.monotonic() - t0, 1),
                            "bytes": out.stat().st_size if out.exists() else 0, "err": p.stderr[-250:] if p.returncode else None}

# 3) Kokoro (onnx)
try:
    subprocess.run(["sudo", "apt-get", "install", "-y", "-qq", "espeak-ng"], capture_output=True)
    p = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "kokoro-onnx", "soundfile"], capture_output=True, text=True)
    base = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
    for f in ("kokoro-v1.0.onnx", "voices-v1.0.bin"):
        urllib.request.urlretrieve(base + f, f)
    import soundfile as sf
    from kokoro_onnx import Kokoro
    k = Kokoro("kokoro-v1.0.onnx", "voices-v1.0.bin")
    for voice in ("pf_dora", "pm_alex", "pm_santa"):
        t0 = time.monotonic()
        samples, sr = k.create(TEXT, voice=voice, speed=0.95, lang="pt-br")
        out = OUT / f"kokoro_{voice}.wav"
        sf.write(out, samples, sr)
        secs = time.monotonic() - t0
        d = len(samples) / sr
        res[f"kokoro:{voice}"] = {"sec": round(secs, 1), "audio_sec": round(d, 1), "rtf": round(secs / d, 2)}
except Exception as e:
    res["kokoro"] = {"error": str(e)[-400:]}

md = "# TTS alternativos\n\n```json\n" + json.dumps(res, indent=2, ensure_ascii=False) + "\n```\n"
save("tts2", res, md)
print(md)
