import io
from datetime import datetime, timezone

import pytest

from app.workers import runner
from app.workers.errors import PermanentError, WaitQuota
from app.workers.handlers import generate_thumbnail as gt

NOW = datetime(2026, 11, 13, 15, 0, tzinfo=timezone.utc)
GOOD = {"headline": ["o oposto do", "buraco negro?"], "highlight": "buraco", "vs": True, "image_prompt": "black hole vs white hole",
        "labels": [{"text": "engole tudo", "side": "left"}, {"text": "expulse tudo?", "side": "right"}, {"text": "extra", "side": "left"}]}


def test_validate_normalizes():
    s = gt.validate(GOOD)
    assert s["headline"] == ["O OPOSTO DO", "BURACO NEGRO?"] and s["highlight"] == "BURACO"
    assert [l["side"] for l in s["labels"]] == ["left", "right"] and s["vs"] is True


def test_validate_drops_bad_pieces():
    s = gt.validate({**GOOD, "highlight": "inexistente", "labels": [{"text": "x" * 40, "side": "left"}], "vs": True})
    assert s["highlight"] is None and s["labels"] == [] and s["vs"] is False  # vs exige 2 rotulos


@pytest.mark.parametrize("bad", [None, {}, {"headline": ["A" * 40], "image_prompt": "x"}, {"headline": ["OK"]}])
def test_validate_rejects(bad):
    with pytest.raises(PermanentError):
        gt.validate(bad)


class Db:
    def __init__(self, used=0):
        self.used, self.uploads, self.rows = used, [], []

    def select(self, table, q=""):
        return {"projects": [{"title": "T", "channel_id": "c"}], "channels": [{"name": "Mundo", "audience": "geral"}],
                "scenes": [{"narration_text": "Texto da cena."}]}[table]

    def count(self, *a):
        return self.used

    def upload(self, *a):
        self.uploads.append(a)

    def insert(self, table, rows):
        self.rows += rows


def test_run_generates_and_stores():
    db, calls = Db(), []
    res = gt.run({"project_id": "p", "user_id": "u"}, db, lambda p: GOOD, lambda p: calls.append(p) or b"img", lambda img, spec: b"jpeg" + img, now=NOW)
    assert "no text" in calls[0] and db.uploads[0][2] == b"jpegimg" and db.rows[0]["kind"] == "thumbnail"
    assert db.uploads[0][1].startswith("u/p/thumb-") and res["vs"] is True


def test_run_waits_when_quota_used():
    with pytest.raises(WaitQuota):
        gt.run({"project_id": "p", "user_id": "u"}, Db(used=10_000), lambda p: GOOD, lambda p: b"", lambda i, s: b"", now=NOW)


def test_compose_real_pillow_and_enqueue():
    pytest.importorskip("PIL")
    from PIL import Image
    from app.workers.thumb_compose import compose
    src = io.BytesIO(); Image.new("RGB", (1024, 1024), (30, 60, 200)).save(src, "JPEG")
    out = compose(src.getvalue(), gt.validate(GOOD))
    assert Image.open(io.BytesIO(out)).size == (1280, 720)
    compose(src.getvalue(), {"headline": ["SO UMA LINHA"]})  # sem rotulos/vs/destaque

    class R:
        inserted = []
        def insert_ignore(self, t, rows, c): self.inserted += rows
    r = R()
    runner.enqueue_thumbnail_after_render(r, {"type": "render_final", "project_id": "p", "user_id": "u"})
    runner.enqueue_thumbnail_after_render(r, {"type": "generate_audio", "project_id": "p", "user_id": "u"})
    assert [x["idempotency_key"] for x in r.inserted] == ["thumb:p"] and "generate_thumbnail" in runner.handlers(object())
