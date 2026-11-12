"""Testa Gemini free: modelos, JSON de divisao de cenas, limite de taxa, modelos de imagem."""
import json
import os
import time

from common import request, save, skip

key = os.environ.get("GEMINI_API_KEY")
if not key:
    skip("gemini", "GEMINI_API_KEY ausente")
    raise SystemExit(0)

B = "https://generativelanguage.googleapis.com/v1beta"
H = {"x-goog-api-key": key}
res = {}

st, _, body, _ = request(f"{B}/models?pageSize=200", headers=H)
res["list_http"] = st
models = []
if st == 200:
    models = json.loads(body).get("models", [])
names = [m["name"].split("/")[-1] for m in models if "generateContent" in m.get("supportedGenerationMethods", [])]
res["models_generateContent"] = names
text_models = [n for n in names if "flash" in n and not any(x in n for x in ("image", "tts", "live", "audio", "preview-0", "exp"))]
res["image_like_models"] = [n for n in names if "image" in n or "imagen" in n]
pick = next((n for n in text_models if "lite" in n), text_models[0] if text_models else None)
res["picked_text_model"] = pick

script = ("Em 1986, um farol abandonado na costa da Noruega voltou a emitir luz. Ninguem sabia quem o acendera. "
          "Os pescadores contam que, nas noites de nevoeiro, uma sombra caminha pela galeria.")
prompt = ("Divida o roteiro em cenas. Responda SOMENTE JSON: lista de objetos com "
          "narration, image_prompt (ingles, estilo documentario sombrio), camera_move. Roteiro: " + script)

if pick:
    st, _, body, secs = request(f"{B}/models/{pick}:generateContent", method="POST", headers=H, timeout=90,
                                body={"contents": [{"parts": [{"text": prompt}]}],
                                      "generationConfig": {"responseMimeType": "application/json"}})
    res["scene_split"] = {"http": st, "sec": round(secs, 2)}
    try:
        txt = json.loads(body)["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(txt)
        res["scene_split"].update(valid_json=True, scenes=len(parsed), sample=parsed[:2])
    except Exception as e:
        res["scene_split"].update(valid_json=False, raw=body[:300].decode("utf-8", "replace"), err=str(e))

    # rajada de chamadas para ver o limite por minuto
    codes = []
    for _ in range(12):
        st, hd, body, _ = request(f"{B}/models/{pick}:generateContent", method="POST", headers=H, timeout=60,
                                  body={"contents": [{"parts": [{"text": "Diga ok."}]}]})
        codes.append(st)
        if st == 429:
            res["first_429_msg"] = body[:400].decode("utf-8", "replace")
            break
    res["burst_codes"] = codes

# sonda de modelos de imagem (apenas verifica se a chave free pode usar)
probe = {}
for n in res["image_like_models"][:3]:
    st, _, body, _ = request(f"{B}/models/{n}:generateContent", method="POST", headers=H, timeout=60,
                             body={"contents": [{"parts": [{"text": "a lighthouse at night"}]}]})
    probe[n] = {"http": st, "msg": body[:200].decode("utf-8", "replace") if st != 200 else "ok"}
res["image_probe"] = probe

md = "# Gemini\n\n```json\n" + json.dumps(res, indent=2, ensure_ascii=False)[:6000] + "\n```\n"
save("gemini", res, md)
print(md)
