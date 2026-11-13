"""Capa estilo YouTube: o Gemini define titulo/destaque/rotulos/prompt, o FLUX gera o fundo e o Pillow desenha o texto."""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone

from ...providers.base import CostTier, UsageEstimate
from ...providers.cost_guard import Decision, check
from ..errors import PermanentError, WaitQuota
from .generate_image import daily_limit

BG_SUFFIX = ", ultra vivid saturated colors, dramatic cinematic lighting, strong contrast, glowing, highly detailed, wide 16:9 composition, empty space at the top, no text, no letters, no watermark"
MAX_LINE, MAX_LABEL = 18, 16


def build_prompt(title: str, channel: dict, script: str) -> str:
    return f"""Voce cria CAPAS de YouTube de alto CTR para o canal "{channel.get('name', '')}" (publico: {channel.get('audience') or 'geral'}).
Video: {title}
Responda SOMENTE JSON:
{{"headline": ["linha 1", "linha 2"],
  "highlight": "UMA palavra da headline para destacar em amarelo",
  "labels": [{{"text": "ate 16 caracteres", "side": "left"}}, {{"text": "ate 16 caracteres", "side": "right"}}],
  "vs": true,
  "image_prompt": "..."}}
Regras:
- headline: 1 a 2 linhas em MAIUSCULAS, ate {MAX_LINE} caracteres cada, gera curiosidade SEM mentir sobre o video (ex.: "O OPOSTO DO" / "BURACO NEGRO?").
- labels: use 2 rotulos curtos (left/right) quando o video compara ou contrapoe duas ideias; senao use lista vazia. vs=true so quando houver comparacao.
- image_prompt: em INGLES, fundo dramatico e muito vivo; se houver comparacao, lado esquerdo e direito bem distintos (ex.: laranja/fogo vs azul/gelo), sujeitos grandes e centrados em cada lado, espaco livre no topo. Sem texto, sem letras, sem pessoas reais.

RESUMO DA NARRACAO:
{script}"""


def validate(r) -> dict:
    if not isinstance(r, dict):
        raise PermanentError("capa: resposta invalida do modelo")
    lines = [re.sub(r"\s+", " ", str(x)).strip().upper() for x in (r.get("headline") or []) if str(x).strip()][:2]
    if not lines or any(len(x) > MAX_LINE + 4 for x in lines):
        raise PermanentError("capa: headline invalida")
    words = {w.strip("?!.,:;") for x in lines for w in x.split()}
    hl = str(r.get("highlight") or "").strip().upper().strip("?!.,:;")
    labels = []
    for lb in r.get("labels") or []:
        t = re.sub(r"\s+", " ", str(lb.get("text", ""))).strip().upper() if isinstance(lb, dict) else ""
        side = lb.get("side") if isinstance(lb, dict) else None
        if t and len(t) <= MAX_LABEL + 4 and side in ("left", "right") and all(x["side"] != side for x in labels):
            labels.append({"text": t, "side": side})
    prompt = str(r.get("image_prompt") or "").strip()
    if not prompt:
        raise PermanentError("capa: sem image_prompt")
    return {"headline": lines, "highlight": hl if hl in words else None, "labels": labels, "vs": bool(r.get("vs")) and len(labels) == 2,
            "image_prompt": prompt}


def run(task: dict, db, llm, flux, compose, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    pid, uid = task["project_id"], task["user_id"]
    proj = db.select("projects", f"id=eq.{pid}&select=title,channel_id")
    if not proj:
        raise PermanentError("projeto nao encontrado")
    ch = db.select("channels", f"id=eq.{proj[0]['channel_id']}&select=name,audience") or [{}]
    scenes = db.select("scenes", f"project_id=eq.{pid}&deleted_at=is.null&order=position&select=narration_text")
    if not scenes:
        raise PermanentError("projeto sem cenas")
    script = " ".join(s["narration_text"] for s in scenes)[:4000]
    spec = validate(llm(build_prompt(proj[0]["title"], ch[0], script)))

    midnight = now.astimezone(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")
    used = db.count("tasks", f"type=eq.generate_image&status=eq.COMPLETED&updated_at=gte.{midnight}")
    guard = check(tier=CostTier.FREE, authorized=True, estimate=UsageEstimate("image", 1), used_today=used,
                  daily_limit=None, conservative_limit=daily_limit(), now=now)
    if guard.decision is Decision.WAIT_QUOTA:
        raise WaitQuota(guard.retry_after, guard.reason)

    jpeg = compose(flux(spec["image_prompt"] + BG_SUFFIX), spec)
    key = f"{uid}/{pid}/thumb-{int(time.time())}.jpg"
    db.upload("media", key, jpeg, "image/jpeg")
    db.insert("media_assets", [{"user_id": uid, "project_id": pid, "kind": "thumbnail", "storage_backend": "supabase", "storage_key": key,
                                "bytes": len(jpeg), "provider": "cloudflare-flux-1-schnell+pillow", "is_intermediate": False,
                                "license": "capa gerada por IA (FLUX.1 schnell, Apache-2.0)"}])
    return {"key": key, "labels": len(spec["labels"]), "vs": spec["vs"]}
