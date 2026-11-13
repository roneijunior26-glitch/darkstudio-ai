"""Gera titulos, descricao (com capitulos reais), tags e hashtags para o YouTube a partir da narracao."""
from __future__ import annotations

import re

from ..errors import PermanentError
from ..render import PAD_S

MAX_TITLE, MAX_TAGS_CHARS, MAX_SCRIPT_CHARS = 100, 480, 14000


def fmt_ts(sec: float) -> str:
    s = int(sec)
    h, m, s = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def chapter_lines(chapters: list[dict], scenes: list[dict]) -> list[str]:
    """Marcacao '0:00 Titulo' com os tempos reais do video (duracao da cena + pad). Vazio se nao der para o YouTube aceitar."""
    starts, t, first = {}, 0.0, {}
    for s in scenes:
        if s.get("chapter_id") and s["chapter_id"] not in first:
            first[s["chapter_id"]] = t
        t += float(s.get("duration_s") or 0) + PAD_S
    out = [(first[c["id"]], c["title"]) for c in chapters if c["id"] in first]
    if len(out) < 3 or any(b[0] - a[0] < 10 for a, b in zip(out, out[1:])):
        return []
    out[0] = (0.0, out[0][1])
    return [f"{fmt_ts(ts)} {title}" for ts, title in out]


def build_prompt(title: str, channel: dict, script: str) -> str:
    return f"""Voce e especialista em SEO de YouTube para canais dark em portugues do Brasil.
Canal: {channel.get('name', '')} | tom: {channel.get('tone') or 'documental'} | publico: {channel.get('audience') or 'geral'}
Titulo de trabalho do video: {title}

Com base na narracao abaixo, responda SOMENTE JSON:
{{"titles": ["3 opcoes de titulo, ate 70 caracteres, que despertam curiosidade SEM mentir sobre o conteudo"],
  "description": "2 a 3 paragrafos curtos: gancho nas 2 primeiras linhas (aparecem na busca), resumo honesto do que o video mostra, chamada para se inscrever",
  "tags": ["10 a 15 tags relevantes, sem #, minusculas"],
  "hashtags": ["3 hashtags com #"]}}

NARRACAO:
{script[:MAX_SCRIPT_CHARS]}"""


def clean(result: dict, chapters: list[str]) -> dict:
    if not isinstance(result, dict):
        raise PermanentError("SEO: resposta invalida do modelo")
    titles = [str(t).strip()[:MAX_TITLE] for t in result.get("titles") or [] if str(t).strip()][:3]
    desc = str(result.get("description") or "").strip()
    if not titles or not desc:
        raise PermanentError("SEO: sem titulos ou descricao")
    tags, total = [], 0
    for t in result.get("tags") or []:
        t = re.sub(r"[#<>]", "", str(t)).strip().lower()
        if t and t not in tags and total + len(t) + 1 <= MAX_TAGS_CHARS:
            tags.append(t); total += len(t) + 1
    hashtags = [("#" + re.sub(r"\W", "", str(h))) for h in (result.get("hashtags") or []) if re.sub(r"\W", "", str(h))][:3]
    full = desc + (("\n\nCAPÍTULOS\n" + "\n".join(chapters)) if chapters else "") + (("\n\n" + " ".join(hashtags)) if hashtags else "")
    return {"titles": titles, "description": full, "tags": tags, "hashtags": hashtags}


def run(task: dict, db, llm) -> dict:
    pid = task["project_id"]
    proj = db.select("projects", f"id=eq.{pid}&select=title,channel_id")
    if not proj:
        raise PermanentError("projeto nao encontrado")
    ch = db.select("channels", f"id=eq.{proj[0]['channel_id']}&select=name,tone,audience") or [{}]
    scenes = db.select("scenes", f"project_id=eq.{pid}&deleted_at=is.null&order=position&select=chapter_id,narration_text,duration_s")
    chapters = db.select("chapters", f"project_id=eq.{pid}&order=position&select=id,title")
    if not scenes:
        raise PermanentError("projeto sem cenas")
    script = " ".join(s["narration_text"] for s in scenes)
    seo = clean(llm(build_prompt(proj[0]["title"], ch[0], script)), chapter_lines(chapters, scenes))
    db.update("projects", f"id=eq.{pid}", {"seo": seo})
    return {"titles": len(seo["titles"]), "tags": len(seo["tags"]), "chapters": "CAPÍTULOS" in seo["description"]}
