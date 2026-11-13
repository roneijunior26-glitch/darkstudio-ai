"""Divide o roteiro colado em capitulos e cenas (narracao fiel ao texto original)."""
from __future__ import annotations

import re

CAMERA = {"slow_zoom_in", "slow_zoom_out", "pan_left", "pan_right", "static"}
TRANSITIONS = {"fade", "cut"}
WORDS_PER_SECOND = 2.5  # ~150 palavras/min


class SplitError(ValueError):
    pass


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def build_prompt(script: str, visual_style: str | None) -> str:
    style = visual_style or "dark cinematic documentary"
    return f"""Voce e um diretor de documentarios para canais dark do YouTube.
Divida o roteiro abaixo em CAPITULOS e CENAS. Regras:
- A narracao de cada cena deve ser um trecho do roteiro COPIADO LITERALMENTE, sem resumir, reescrever ou omitir nada.
  Juntas, as cenas devem cobrir o roteiro inteiro, na ordem.
- Cada cena tem de 15 a 25 palavras de narracao (cerca de 6 a 10 segundos), terminando em fim de frase quando possivel.
- image_prompt: em INGLES, descreve UMA imagem estatica (sem texto na imagem, sem pessoas reais identificaveis),
  assunto principal CENTRALIZADO, boa iluminacao e contraste (nao escura demais), estilo: {style}.
- camera_move: um de slow_zoom_in, slow_zoom_out, pan_left, pan_right, static.
- transition: fade ou cut.
Responda SOMENTE JSON no formato:
{{"chapters":[{{"title":"...","scenes":[{{"narration":"...","image_prompt":"...","camera_move":"slow_zoom_in","transition":"fade"}}]}}]}}

ROTEIRO:
{script}"""


def validate(result, script: str, min_coverage: float = 0.95):
    """Valida o JSON do modelo e devolve lista de capitulos limpa. Levanta SplitError se invalido."""
    if not isinstance(result, dict) or not isinstance(result.get("chapters"), list) or not result["chapters"]:
        raise SplitError("JSON sem 'chapters'")
    chapters, total_words = [], 0
    for ci, ch in enumerate(result["chapters"], 1):
        scenes = []
        for sc in ch.get("scenes", []) if isinstance(ch, dict) else []:
            narr = str(sc.get("narration", "")).strip()
            prompt = str(sc.get("image_prompt", "")).strip()
            if not narr or not prompt:
                raise SplitError(f"cena sem narracao ou image_prompt no capitulo {ci}")
            cam = sc.get("camera_move") if sc.get("camera_move") in CAMERA else "slow_zoom_in"
            tr = sc.get("transition") if sc.get("transition") in TRANSITIONS else "fade"
            total_words += len(_words(narr))
            scenes.append({"narration": narr, "image_prompt": prompt, "camera_move": cam, "transition": tr})
        if scenes:
            chapters.append({"title": str(ch.get("title") or f"Capitulo {ci}")[:200], "scenes": scenes})
    if not chapters:
        raise SplitError("nenhuma cena valida")
    original = len(_words(script))
    if original and total_words < original * min_coverage:
        raise SplitError(f"narracao cobre {total_words}/{original} palavras do roteiro (minimo {min_coverage:.0%})")
    return chapters


def run(task: dict, db, llm) -> dict:
    """Executa a tarefa. `db` = Rest, `llm` = funcao(prompt)->dict (injetavel para testes)."""
    ver_id = task["payload"]["script_version_id"]
    project_id = task["project_id"]
    uid = task["user_id"]
    ver = db.select("script_versions", f"id=eq.{ver_id}&select=content")
    if not ver:
        raise SplitError("versao do roteiro nao encontrada")
    script = ver[0]["content"]
    proj = db.select("projects", f"id=eq.{project_id}&select=visual_style")[0]

    chapters = validate(llm(build_prompt(script, proj.get("visual_style"))), script)

    # idempotente: refaz do zero se a tarefa for repetida
    db.delete("scenes", f"project_id=eq.{project_id}")
    db.delete("chapters", f"project_id=eq.{project_id}")
    ch_rows = db.insert("chapters", [{"user_id": uid, "project_id": project_id, "position": i, "title": c["title"],
                                       "text": " ".join(s["narration"] for s in c["scenes"])}
                                      for i, c in enumerate(chapters, 1)])
    scene_rows, pos = [], 0
    for ch_row, c in zip(ch_rows, chapters):
        for s in c["scenes"]:
            pos += 1
            scene_rows.append({"user_id": uid, "project_id": project_id, "chapter_id": ch_row["id"], "position": pos,
                               "narration_text": s["narration"], "image_prompt": s["image_prompt"],
                               "camera_move": s["camera_move"], "transition": s["transition"],
                               "est_duration_s": round(len(_words(s["narration"])) / WORDS_PER_SECOND, 1)})
    db.insert("scenes", scene_rows)
    db.update("projects", f"id=eq.{project_id}", {"status": "storyboard"})
    # o usuario revisa o storyboard antes de gastar cota com imagens
    db.insert("tasks", [{"user_id": uid, "project_id": project_id, "type": "approve_storyboard",
                         "status": "WAITING_APPROVAL", "payload": {}, "idempotency_key": f"approve:{ver_id}"}])
    return {"chapters": len(chapters), "scenes": len(scene_rows)}
