import pytest

from app.workers.handlers import split_scenes as ss

SCRIPT = "Em 1986 um farol abandonado voltou a emitir luz. Ninguem sabia quem o acendera. Os pescadores evitavam falar do assunto."


def good():
    return {"chapters": [{"title": "Abertura", "scenes": [
        {"narration": "Em 1986 um farol abandonado voltou a emitir luz.", "image_prompt": "lighthouse", "camera_move": "pan_left", "transition": "cut"},
        {"narration": "Ninguem sabia quem o acendera. Os pescadores evitavam falar do assunto.", "image_prompt": "fishermen", "camera_move": "invalid", "transition": "xx"}]}]}


def test_validate_ok_and_defaults():
    ch = ss.validate(good(), SCRIPT)
    assert len(ch[0]["scenes"]) == 2
    assert ch[0]["scenes"][1]["camera_move"] == "slow_zoom_in" and ch[0]["scenes"][1]["transition"] == "fade"


def test_validate_rejects_low_coverage():
    r = good()
    r["chapters"][0]["scenes"].pop()
    with pytest.raises(ss.SplitError, match="cobre"):
        ss.validate(r, SCRIPT)


@pytest.mark.parametrize("bad", [None, {}, {"chapters": []}, {"chapters": [{"scenes": [{"narration": "x"}]}]}])
def test_validate_rejects_bad_shapes(bad):
    with pytest.raises(ss.SplitError):
        ss.validate(bad, SCRIPT)


class FakeDb:
    def __init__(self):
        self.t = {"script_versions": [{"id": "v1", "content": SCRIPT}], "projects": [{"id": "p1", "visual_style": "dark"}],
                  "chapters": [], "scenes": [], "tasks": []}
        self.updates = []

    def select(self, table, q=""):
        return self.t[table]

    def insert(self, table, rows):
        rows = [dict(r, id=f"{table}-{len(self.t[table]) + i}") for i, r in enumerate(rows)]
        self.t[table] += rows
        return rows

    def update(self, table, q, v):
        self.updates.append((table, q, v))

    def delete(self, table, q):
        self.t[table] = []


def test_run_creates_chapters_scenes_and_image_tasks():
    db = FakeDb()
    task = {"payload": {"script_version_id": "v1"}, "project_id": "p1", "user_id": "u1"}
    res = ss.run(task, db, lambda prompt: good())
    assert res == {"chapters": 1, "scenes": 2}
    assert [s["position"] for s in db.t["scenes"]] == [1, 2]
    assert db.t["scenes"][0]["chapter_id"] == db.t["chapters"][0]["id"]
    assert [t["type"] for t in db.t["tasks"]] == ["generate_image", "generate_image"]
    assert db.t["tasks"][0]["payload"]["scene_id"] == db.t["scenes"][0]["id"]
    assert db.t["tasks"][0]["idempotency_key"] == f"img:{db.t['scenes'][0]['id']}"
    assert ("projects", "id=eq.p1", {"status": "producing"}) in db.updates
