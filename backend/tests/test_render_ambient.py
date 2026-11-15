import shutil
import subprocess

import pytest

from app.workers import render
from app.workers.errors import PermanentError
from app.workers.handlers import render_ambient

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg ausente")


def probe(path, entries):
    return subprocess.run(["ffprobe", "-v", "error", "-show_entries", entries, "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout.strip()


def test_hours_validation():
    assert render_ambient.hours_of({"hours": "2"}) == 2.0
    for bad in (None, "x", 0, 11):
        with pytest.raises(PermanentError):
            render_ambient.hours_of({"hours": bad})


@needs_ffmpeg
def test_loop_unit_and_ambient_video(tmp_path):
    src, img, logo = tmp_path / "chuva.wav", tmp_path / "i.jpg", tmp_path / "l.png"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anoisesrc=d=20:c=pink:r=44100", str(src)], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=1280x720", "-frames:v", "1", str(img)], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=red:s=200x200", "-frames:v", "1", str(logo)], check=True)
    loop = tmp_path / "loop.wav"
    unit = render.make_loop_unit(src, loop)
    assert 15.5 < unit < 16.5 and 15.5 < render.audio_duration(loop) < 16.5  # 20 s - 4 s de crossfade
    out = tmp_path / "o.mp4"
    render.render_ambient(img, loop, 50.0, out, logo)  # 50 s > 16 s: a trilha repete
    assert probe(out, "stream=codec_name,width,height") .splitlines() in (["h264,1920,1080", "aac"], ["aac", "h264,1920,1080"]) or "h264,1920,1080" in probe(out, "stream=codec_name,width,height")
    assert 49.5 < float(probe(out, "format=duration")) < 50.6
    assert out.stat().st_size < 3_000_000  # quadro parado: arquivo pequeno


class FakeDb:
    def __init__(self):
        self.rows, self.updates, self.uploads, self.store = {}, [], [], {}

    def select(self, table, q):
        if table == "projects":
            return [{"title": "Chuva: 1h?", "channel_id": None}]
        if table == "music_assets":
            return [{"name": "Chuva", "storage_key": "u/music/c.wav"}]
        return []

    def insert(self, table, rows):
        self.rows.setdefault(table, []).extend(rows)
        return [{**r, "id": f"{table}-id"} for r in rows]

    def update(self, table, q, v):
        self.updates.append(v)

    def upload(self, bucket, key, data, ctype):
        self.uploads.append(key)
        self.store[key] = data


@needs_ffmpeg
def test_handler_generates_image_and_publishes(tmp_path):
    from app.workers import tts
    wav = tts.pcm_to_wav(b"\x10\x00" * 24000 * 20, 24000)  # 20 s
    jpg = tmp_path / "i.jpg"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=1024x1024", "-frames:v", "1", str(jpg)], check=True)
    db = FakeDb()
    store = db.store
    store["u/music/c.wav"] = wav
    pub = lambda path, name: {"backend": "gdrive", "key": "D1", "url": "https://x", "name": name}
    t = {"project_id": "p", "user_id": "u", "payload": {"track_id": "t1", "hours": 0.05, "image_prompt": "rain on a window"}}
    res = render_ambient.run(t, db, lambda b, k: store[k], lambda prompt: jpg.read_bytes(), outdir=str(tmp_path / "out"), publish=pub)
    assert res["duration_s"] == 180 and res["stored_in"] == "gdrive"
    assert db.updates[0]["status"] == "rendering" and db.updates[-1]["status"] == "awaiting_approval"
    kinds = [r["kind"] for k in ("media_assets",) for r in db.rows[k]]
    assert kinds == ["image", "thumbnail", "export"] and db.rows["project_exports"][0]["asset_id"] == "media_assets-id"
    assert 178 < float(probe(tmp_path / "out" / "p.mp4", "format=duration")) < 181
