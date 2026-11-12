"""Testa Piper pt-BR: qualidade (arquivo de audio fica so no artifact), velocidade e licenca."""
import json
import pathlib
import subprocess
import sys
import time
import wave

from common import OUT, request, save

VOICES = [("pt_BR-faber-medium", "faber/medium"), ("pt_BR-edresson-low", "edresson/low"),
          ("pt_BR-cadu-medium", "cadu/medium"), ("pt_BR-jeff-medium", "jeff/medium")]
TEXT = ("Em mil novecentos e oitenta e seis, um farol abandonado na costa da Noruega voltou a emitir luz. "
        "Ninguem sabia quem o acendera, e os pescadores evitavam falar do assunto.")
vdir = pathlib.Path("voices")
vdir.mkdir(exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)
res = {}
for voice, path in VOICES:
    r = {}
    p = subprocess.run([sys.executable, "-m", "piper.download_voices", voice], cwd=vdir, capture_output=True, text=True)
    r["download_rc"] = p.returncode
    if p.returncode:
        r["download_err"] = p.stderr[-300:]
        res[voice] = r
        continue
    out = OUT / f"tts_{voice}.wav"
    t0 = time.monotonic()
    p = subprocess.run([sys.executable, "-m", "piper", "-m", voice, "--data-dir", str(vdir), "-f", str(out), "--", TEXT],
                       capture_output=True, text=True)
    secs = time.monotonic() - t0
    r["synth_rc"], r["synth_sec"] = p.returncode, round(secs, 2)
    if p.returncode == 0 and out.exists():
        with wave.open(str(out)) as w:
            dur = w.getnframes() / w.getframerate()
        r["audio_sec"], r["real_time_factor"] = round(dur, 2), round(secs / dur, 3)
    else:
        r["synth_err"] = p.stderr[-300:]
    st, _, body, _ = request(f"https://huggingface.co/rhasspy/piper-voices/raw/main/pt/pt_BR/{path}/MODEL_CARD")
    r["model_card_http"] = st
    r["model_card_head"] = body[:700].decode("utf-8", "replace") if st == 200 else None
    res[voice] = r
md = "# TTS Piper pt-BR\n\nOuvir os .wav no artifact `results-tts`.\n\n```json\n" + json.dumps(res, indent=2, ensure_ascii=False) + "\n```\n"
save("tts", res, md)
print(md)
