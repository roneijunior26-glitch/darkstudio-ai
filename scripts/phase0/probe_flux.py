"""Testa Cloudflare Workers AI (FLUX-1-schnell): latencia, formato, capacidade diaria."""
import base64
import os
import struct

from common import OUT, request, save, skip

acct, tok = os.environ.get("CLOUDFLARE_ACCOUNT_ID"), os.environ.get("CLOUDFLARE_API_TOKEN")
if not acct or not tok:
    skip("flux", "CLOUDFLARE_ACCOUNT_ID/CLOUDFLARE_API_TOKEN ausentes")
    raise SystemExit(0)

MAX = int(os.environ.get("MAX_IMAGES", "3"))
DRAIN = os.environ.get("DRAIN") == "true"
limit = 400 if DRAIN else MAX
url = f"https://api.cloudflare.com/client/v4/accounts/{acct}/ai/run/@cf/black-forest-labs/flux-1-schnell"
H = {"Authorization": f"Bearer {tok}"}
prompt = "dark cinematic documentary still, abandoned lighthouse at night, fog, moody lighting, 16:9"

st, _, body, _ = request(f"https://api.cloudflare.com/client/v4/accounts/{acct}/tokens/verify", headers=H)
verify = {"http": st, "body": body[:300].decode("utf-8", "replace")}
print("verify token:", verify)
runs, ok, stop_reason = [], 0, None
for i in range(limit):
    st, hd, body, secs = request(url, method="POST", headers=H, body={"prompt": prompt, "steps": 4}, timeout=180)
    row = {"i": i, "http": st, "sec": round(secs, 2)}
    if st == 200:
        img = None
        try:
            import json
            j = json.loads(body)
            b64 = (j.get("result") or j).get("image")
            img = base64.b64decode(b64) if b64 else None
        except Exception:
            img = body if body[:2] in (b"\xff\xd8", b"\x89P") else None
        if img:
            ok += 1
            row["bytes"] = len(img)
            if img[:2] == b"\xff\xd8":
                row["format"] = "jpeg"
            elif img[:4] == b"\x89PNG":
                row["format"] = "png"
                row["size"] = struct.unpack(">II", img[16:24])
            if i == 0:  # so a primeira imagem fica nos artifacts (nao vai ao branch)
                (OUT / "sample_flux.bin").write_bytes(img)
        else:
            row["note"] = "200 sem imagem reconhecivel"
    else:
        row["error"] = body[:300].decode("utf-8", "replace")
        stop_reason = f"HTTP {st}"
        runs.append(row)
        break
    runs.append(row)

res = {"token_verify": verify, "account_id_len": len(acct), "token_len": len(tok), "images_ok": ok, "requested_limit": limit, "drain": DRAIN, "stop_reason": stop_reason, "runs": runs[:30],
       "avg_sec": round(sum(r["sec"] for r in runs) / max(len(runs), 1), 2),
       "note": "Se DRAIN=true e parou por HTTP 429/4xx, images_ok ~ capacidade diaria real (10k neurons)."}
md = (f"# FLUX (Cloudflare)\n\n- imagens geradas: **{ok}**\n- parou por: {stop_reason}\n"
      f"- latencia media: {res['avg_sec']} s\n- primeira resposta: {runs[0] if runs else None}\n")
save("flux", res, md)
print(md)
