"""Loop do worker: reserva tarefas na fila, executa e registra sucesso/falha com retry."""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from . import cloudflare, gemini, tts
from .errors import PermanentError, WaitQuota
from .handlers import generate_audio, generate_image, split_scenes
from .queue import retry_at, status_after_failure
from .rest import Rest


def redact(text: str) -> str:
    for name in ("SUPABASE_SERVICE_KEY", "GEMINI_API_KEY", "CLOUDFLARE_API_TOKEN"):
        val = os.environ.get(name, "")
        if len(val) >= 6:
            text = text.replace(val, f"<{name}>")
    return text


def handlers(db: Rest):
    return {
        "split_scenes": lambda t: split_scenes.run(t, db, gemini.generate_json),
        "generate_image": lambda t: generate_image.run(t, db, cloudflare.generate),
        "generate_audio": lambda t: generate_audio.run(t, db, tts.synthesize),
    }


def finish(db: Rest, task: dict, error: Exception | None, result: dict | None = None, permanent=False):
    tid = task["id"]
    if isinstance(error, WaitQuota):  # espera a cota voltar; nao conta como tentativa
        db.update("tasks", f"id=eq.{tid}", {"status": "WAITING_PROVIDER", "run_after": error.until.isoformat(),
                                            "attempts": max(task["attempts"] - 1, 0), "last_error": str(error)[:300],
                                            "locked_by": None, "locked_at": None})
        return
    if error is None:
        db.update("tasks", f"id=eq.{tid}", {"status": "COMPLETED", "result": result, "last_error": None,
                                            "locked_by": None, "locked_at": None})
        return
    msg = redact(f"{type(error).__name__}: {error}")[:500]
    status = "FAILED" if permanent else status_after_failure(task["attempts"], task["max_attempts"]).value
    values = {"status": status, "last_error": msg, "locked_by": None, "locked_at": None}
    if status == "QUEUED":
        values["run_after"] = retry_at(datetime.now(timezone.utc), task["attempts"]).isoformat()
    db.update("tasks", f"id=eq.{tid}", values)


def run(db: Rest | None = None, max_seconds: int | None = None) -> int:
    db = db or Rest()
    max_seconds = max_seconds or int(os.environ.get("WORKER_MAX_SECONDS", "3000"))
    worker = f"gha-{os.environ.get('GITHUB_RUN_ID', 'local')}"
    reg = handlers(db)
    started, done = time.monotonic(), 0
    db.rpc("reclaim_stuck_tasks")
    while time.monotonic() - started < max_seconds:
        claimed = db.rpc("claim_task", {"p_worker": worker})
        if not claimed:
            break
        task = claimed[0]
        print(f"[worker] {task['type']} {task['id']} (tentativa {task['attempts']})", flush=True)
        try:
            fn = reg.get(task["type"])
            if fn is None:
                raise PermanentError(f"tipo de tarefa desconhecido: {task['type']}")
            finish(db, task, None, fn(task))
            done += 1
        except PermanentError as e:
            finish(db, task, e, permanent=True)
        except WaitQuota as e:
            finish(db, task, e)
            print(f"[worker] cota esgotada, aguardando ate {e.until:%Y-%m-%d %H:%M} UTC", flush=True)
        except Exception as e:  # noqa: BLE001 - qualquer falha vira retry com backoff
            finish(db, task, e)
            print(f"[worker] falhou: {redact(str(e))[:200]}", flush=True)
    print(f"[worker] fim: {done} tarefa(s) concluida(s)")
    return done


if __name__ == "__main__":
    run()
