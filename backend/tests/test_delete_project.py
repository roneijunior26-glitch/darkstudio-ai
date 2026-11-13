import io
import json
import pytest

from app.workers import gh_release, runner
from app.workers.handlers import delete_project as dp

TREE = {"u/p": [{"name": "images", "id": None}, {"name": "audio", "id": None}, {"name": "thumb-1.jpg", "id": "x"}],
        "u/p/images": [{"name": "a.jpg", "id": "1"}], "u/p/audio": [{"name": "a.wav", "id": "2"}]}


class Db:
    def __init__(self, owns=True):
        self.owns, self.removed, self.deleted, self.updates = owns, [], [], []

    def select(self, table, q=""):
        if table == "projects":
            return [{"id": "p"}] if self.owns else []
        return [{"storage_key": "release:video-abc"}, {"storage_key": "video-5"}, {"storage_key": None}]

    def storage_list(self, bucket, prefix):
        return TREE.get(prefix, [])

    def storage_remove(self, bucket, paths):
        self.removed += paths

    def delete(self, table, q):
        self.deleted.append((table, q))

    def update(self, table, q, v):
        self.updates.append((table, q, v))


def test_delete_removes_files_release_and_rows():
    db, rel = Db(), []
    res = dp.run({"user_id": "u", "payload": {"project_id": "p"}}, db, lambda tag: rel.append(tag) or True)
    assert sorted(db.removed) == ["u/p/audio/a.wav", "u/p/images/a.jpg", "u/p/thumb-1.jpg"]
    assert rel == ["video-abc"] and db.deleted == [("projects", "id=eq.p")] and res == {"files": 3, "releases": 1}


def test_free_space_keeps_video_and_cover():
    db = Db()
    res = dp.run({"user_id": "u", "payload": {"project_id": "p", "mode": "free_space"}}, db, lambda t: True)
    assert sorted(db.removed) == ["u/p/audio/a.wav", "u/p/images/a.jpg"] and db.deleted == [] and res["freed_files"] == 2
    assert db.updates[0][1] == "project_id=eq.p&kind=in.(image,audio)"


def test_foreign_or_missing_project_is_skipped_and_bad_mode_rejected():
    assert dp.run({"user_id": "u", "payload": {"project_id": "p"}}, Db(owns=False), lambda t: True) == {"skipped": "projeto nao existe mais"}
    assert dp.run({"user_id": "u", "payload": {}}, Db(), lambda t: True)["skipped"]
    with pytest.raises(Exception, match="modo"):
        dp.run({"user_id": "u", "payload": {"project_id": "p", "mode": "x"}}, Db(), lambda t: True)


def test_registered_and_release_delete(monkeypatch):
    assert "delete_project" in runner.handlers(object())
    monkeypatch.setenv("GITHUB_TOKEN", "t"); monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    calls = []

    class R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake(req, timeout=0):
        calls.append((req.get_method(), req.full_url.split("/repos/o/r")[1]))
        return R(b'{"id": 7}' if req.get_method() == "GET" else b"")
    monkeypatch.setattr("urllib.request.urlopen", fake)
    assert gh_release.delete("video-abc") is True
    assert calls == [("GET", "/releases/tags/video-abc"), ("DELETE", "/releases/7"), ("DELETE", "/git/refs/tags/video-abc")]
