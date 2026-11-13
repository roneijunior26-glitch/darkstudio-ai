import pytest

from app.workers import runner
from app.workers.errors import PermanentError
from app.workers.handlers import generate_seo as g


def sc(i, ch, d=20.0):
    return {"chapter_id": ch, "narration_text": f"Texto {i}.", "duration_s": d}


CH = [{"id": "a", "title": "Abertura"}, {"id": "b", "title": "O horizonte"}, {"id": "c", "title": "Final"}]
SC = [sc(1, "a"), sc(2, "a"), sc(3, "b"), sc(4, "c")]


def test_chapter_timestamps_use_real_durations():
    lines = g.chapter_lines(CH, SC)
    assert lines[0] == "0:00 Abertura" and lines[1].endswith("O horizonte") and lines[2].endswith("Final")
    assert lines[1].startswith("0:40") and lines[2].startswith("1:00")


def test_chapters_omitted_when_youtube_would_reject():
    assert g.chapter_lines(CH[:2], SC) == []  # menos de 3
    assert g.chapter_lines(CH, [sc(1, "a", 3), sc(2, "b", 3), sc(3, "c", 3)]) == []  # capitulos < 10 s


def test_fmt_ts():
    assert g.fmt_ts(59) == "0:59" and g.fmt_ts(3725) == "1:02:05"


def test_clean_limits_and_assembles():
    r = {"titles": ["A" * 150, "B", "C", "D"], "description": "Gancho.\n\nResumo.", "tags": ["Buraco Negro", "#espaço", "buraco negro", "x" * 600],
         "hashtags": ["#Espaco", "ciencia", "!!"]}
    out = g.clean(r, ["0:00 A", "1:00 B", "2:00 C"])
    assert len(out["titles"]) == 3 and len(out["titles"][0]) == 100
    assert out["tags"] == ["buraco negro", "espaço"]
    assert out["hashtags"] == ["#Espaco", "#ciencia"]
    assert "CAPÍTULOS\n0:00 A" in out["description"] and out["description"].endswith("#Espaco #ciencia")


@pytest.mark.parametrize("bad", [None, {}, {"titles": ["x"]}, {"description": "d"}])
def test_clean_rejects(bad):
    with pytest.raises(PermanentError):
        g.clean(bad, [])


class Db:
    def __init__(self):
        self.updates, self.inserted = [], []

    def select(self, table, q=""):
        return {"projects": [{"title": "T", "channel_id": "c"}], "channels": [{"name": "Mundo", "tone": None, "audience": None}],
                "scenes": SC, "chapters": CH}[table]

    def update(self, table, q, v):
        self.updates.append(v)

    def insert_ignore(self, table, rows, conflict):
        self.inserted += rows


def test_run_saves_seo_and_enqueued_after_render():
    db = Db()
    prompts = []
    llm = lambda p: prompts.append(p) or {"titles": ["Titulo"], "description": "Gancho", "tags": ["a"], "hashtags": ["#x"]}
    res = g.run({"project_id": "p"}, db, llm)
    assert res["chapters"] is True and "Mundo" in prompts[0] and "Texto 1." in prompts[0]
    assert db.updates[0]["seo"]["titles"] == ["Titulo"]
    runner.enqueue_seo_after_render(db, {"type": "render_final", "project_id": "p", "user_id": "u"})
    runner.enqueue_seo_after_render(db, {"type": "generate_image", "project_id": "p", "user_id": "u"})
    assert [r["idempotency_key"] for r in db.inserted] == ["seo:p"]
