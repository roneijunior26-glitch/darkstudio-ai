from app.workers import runner


class Db:
    def __init__(self, tasks):
        self.queue, self.updates = list(tasks), []

    def rpc(self, fn, args=None):
        return [self.queue.pop(0)] if fn == "claim_task" and self.queue else ([] if fn == "claim_task" else 0)

    def update(self, table, q, v):
        self.updates.append((q, v))


def task(attempts=1, max_attempts=3, type_="split_scenes"):
    return {"id": "t1", "type": type_, "attempts": attempts, "max_attempts": max_attempts, "payload": {}, "project_id": "p", "user_id": "u"}


def test_unknown_type_fails_permanently():
    db = Db([task(type_="nao_existe")])
    runner.run(db, max_seconds=5)
    q, v = db.updates[-1]
    assert v["status"] == "FAILED" and "desconhecido" in v["last_error"]


def test_failure_requeues_with_backoff(monkeypatch):
    db = Db([task(attempts=1)])
    monkeypatch.setattr(runner, "handlers", lambda d: {"split_scenes": lambda t: (_ for _ in ()).throw(RuntimeError("boom"))})
    runner.run(db, max_seconds=5)
    _, v = db.updates[-1]
    assert v["status"] == "QUEUED" and "run_after" in v and "boom" in v["last_error"]


def test_failure_after_max_attempts_is_failed(monkeypatch):
    db = Db([task(attempts=3)])
    monkeypatch.setattr(runner, "handlers", lambda d: {"split_scenes": lambda t: (_ for _ in ()).throw(RuntimeError("boom"))})
    runner.run(db, max_seconds=5)
    assert db.updates[-1][1]["status"] == "FAILED"


def test_success_marks_completed(monkeypatch):
    db = Db([task()])
    monkeypatch.setattr(runner, "handlers", lambda d: {"split_scenes": lambda t: {"ok": 1}})
    assert runner.run(db, max_seconds=5) == 1
    assert db.updates[-1][1]["status"] == "COMPLETED"


def test_error_message_redacts_secret(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AQ.topsecretvalue99")
    db = Db([task()])
    monkeypatch.setattr(runner, "handlers", lambda d: {"split_scenes": lambda t: (_ for _ in ()).throw(RuntimeError("falha AQ.topsecretvalue99"))})
    runner.run(db, max_seconds=5)
    assert "topsecretvalue" not in db.updates[-1][1]["last_error"]
