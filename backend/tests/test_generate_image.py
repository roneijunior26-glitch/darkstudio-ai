from datetime import datetime, timezone

import pytest

from app.workers import runner
from app.workers.errors import PermanentError, WaitQuota
from app.workers.handlers import generate_image as gi

NOW = datetime(2026, 11, 13, 15, 0, tzinfo=timezone.utc)
JPEG = b"\xff\xd8\xff" + b"x" * 50


class Db:
    def __init__(self, scene=None, used=0):
        self.scene = scene if scene is not None else {"id": "s1", "project_id": "p1", "user_id": "u1", "image_prompt": "farol", "image_asset_id": None}
        self.used, self.uploads, self.assets, self.updates = used, [], [], []

    def select(self, table, q=""):
        return [self.scene] if self.scene else []

    def count(self, table, q=""):
        self.count_queries = getattr(self, "count_queries", []) + [q]
        return self.used

    def upload(self, bucket, path, data, ctype):
        self.uploads.append((bucket, path, ctype))

    def insert(self, table, rows):
        self.assets += rows
        return [{"id": "a1"}]

    def update(self, table, q, v):
        self.updates.append((table, v))


def test_generates_and_registers_asset():
    db = Db()
    prompts = []
    res = gi.run({"payload": {"scene_id": "s1"}}, db, lambda p: prompts.append(p) or JPEG, now=NOW)
    assert res["asset_id"] == "a1"
    assert db.uploads == [("media", "u1/p1/images/s1.jpg", "image/jpeg")]
    assert db.assets[0]["kind"] == "image" and db.assets[0]["is_intermediate"] is True
    assert ("scenes", {"image_asset_id": "a1", "status": "generating"}) in db.updates
    assert prompts[0].startswith("farol") and "no text" in prompts[0]


def test_skips_when_image_exists():
    db = Db(scene={"id": "s1", "project_id": "p", "user_id": "u", "image_prompt": "x", "image_asset_id": "a0"})
    assert gi.run({"payload": {"scene_id": "s1"}}, db, lambda p: 1 / 0, now=NOW) == {"skipped": "imagem ja existe"}


def test_waits_for_quota_until_next_utc_midnight():
    db = Db(used=150)
    with pytest.raises(WaitQuota) as e:
        gi.run({"payload": {"scene_id": "s1"}}, db, lambda p: JPEG, now=NOW)
    assert e.value.until == datetime(2026, 11, 14, 0, 0, tzinfo=timezone.utc)
    assert not db.uploads


def test_missing_scene_is_permanent():
    with pytest.raises(PermanentError):
        gi.run({"payload": {"scene_id": "zz"}}, Db(scene={}), lambda p: JPEG, now=NOW)


class QDb:
    def __init__(self, t):
        self.q, self.updates = [t], []

    def rpc(self, fn, args=None):
        return [self.q.pop(0)] if fn == "claim_task" and self.q else []

    def update(self, table, q, v):
        self.updates.append(v)


def test_runner_puts_task_in_waiting_provider_without_spending_attempt(monkeypatch):
    until = datetime(2026, 11, 14, tzinfo=timezone.utc)
    t = {"id": "t", "type": "generate_image", "attempts": 2, "max_attempts": 3, "payload": {}}
    monkeypatch.setattr(runner, "handlers", lambda d: {"generate_image": lambda task: (_ for _ in ()).throw(WaitQuota(until))})
    db = QDb(t)
    runner.run(db, max_seconds=5)
    v = db.updates[-1]
    assert v["status"] == "WAITING_PROVIDER" and v["attempts"] == 1 and v["run_after"] == until.isoformat()


def test_quota_query_has_no_plus_sign():
    db = Db()
    gi.run({"payload": {"scene_id": "s1"}}, db, lambda p: JPEG, now=NOW)
    assert db.count_queries and all("+" not in q for q in db.count_queries)
    assert "updated_at=gte.2026-11-13T00:00:00Z" in db.count_queries[0]


def test_flux_429_becomes_wait_not_failure():
    from app.workers import cloudflare
    db = Db()

    def flux(prompt):
        raise cloudflare.FluxQuota("HTTP 429: you have used up your daily free allocation of 10,000 neurons")
    with pytest.raises(WaitQuota) as e:
        gi.run({"payload": {"scene_id": "s1"}}, db, flux, now=NOW)
    assert e.value.until == datetime(2026, 11, 14, 0, 5, tzinfo=timezone.utc)
