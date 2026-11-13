import shutil
import subprocess

import pytest

from app.workers import runner
from app.workers.errors import PermanentError
from app.workers.handlers import cut_video as cv

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="sem ffmpeg")
URL = "https://github.com/o/r/releases/download/video-x/v.mp4"


def test_validate():
    assert cv.validate([{"in": 1, "out": 5.5}]) == [(1.0, 5.5)]
    for bad in (None, [], [{"in": 5, "out": 5}], [{"in": -1, "out": 2}], [{"in": "a", "out": 2}], [{"out": 2}],
                [{"in": 0, "out": 5}] * 21, [{"in": 0, "out": 4000}]):
        with pytest.raises(PermanentError):
            cv.validate(bad)


def test_cut_args_modes():
    fast = cv.cut_args("s.mp4", 1, 4, "o.mp4", False, False)
    assert "copy" in fast and "-filter_complex" not in fast
    prec = cv.cut_args("s.mp4", 1, 4, "o.mp4", True, False)
    assert "libx264" in prec and "-filter_complex" not in prec
    vert = cv.cut_args("s.mp4", 1, 4, "o.mp4", False, True)  # vertical sempre recodifica
    assert "libx264" in vert and "1080:1920" in vert[vert.index("-filter_complex") + 1]


class Db:
    def __init__(self, cut, url=URL):
        self.cut, self.url, self.updates, self.assets = cut, url, [], []

    def select(self, table, q=""):
        return {"video_cuts": [self.cut] if self.cut else [], "project_exports": [{"asset_id": "a"}], "media_assets": [{"origin_url": self.url}]}[table]

    def update(self, table, q, v):
        self.updates.append(v)

    def insert(self, table, rows):
        self.assets += rows
        return [{"id": "asset1"}]


def cut(**kw):
    return {"id": "c", "project_id": "p", "export_id": "e", "segments": [{"in": 0.5, "out": 2.0}, {"in": 3, "out": 4.5}], "mode": "fast", "name": "Meu corte", "vertical": False, **kw}


@needs_ffmpeg
@pytest.mark.parametrize("kw,size", [({}, None), ({"mode": "precise"}, None), ({"vertical": True}, "1080,1920")])
def test_real_cut_modes(tmp_path, kw, size):
    src = tmp_path / "src.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=1280x720:r=30:d=6", "-f", "lavfi", "-i", "sine=f=440:d=6",
                    "-c:v", "libx264", "-g", "30", "-c:a", "aac", "-shortest", str(src)], check=True)
    seen = {}

    def publish(path, title):
        seen["size"] = path.stat().st_size
        seen["probe"] = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout
        dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout
        seen["dur"] = float(dur)
        return {"tag": "video-new", "url": "https://github.com/o/r/releases/download/video-new/c.mp4", "bytes": seen["size"]}
    db = Db(cut(**kw))
    res = cv.run({"user_id": "u", "payload": {"cut_id": "c"}}, db, fetch=lambda u, d: shutil.copy(src, d), publish=publish)
    assert res["segments"] == 2 and 2.5 < seen["dur"] < 4.5
    if size:
        assert size in seen["probe"]
    assert db.updates[-1]["status"] == "done" and db.assets[0]["storage_key"] == "release:video-new"


def test_old_video_without_release_is_permanent_error_and_marked_failed():
    db = Db(cut(), url="https://github.com/o/r/actions/runs/5")
    with pytest.raises(PermanentError, match="download direto"):
        cv.run({"user_id": "u", "payload": {"cut_id": "c"}}, db, fetch=lambda *a: None, publish=None)
    assert db.updates[-1]["status"] == "failed" and "download direto" in db.updates[-1]["error"]


def test_missing_cut_and_registered():
    with pytest.raises(PermanentError):
        cv.run({"user_id": "u", "payload": {}}, Db(None))
    assert "cut_video" in runner.handlers(object())
