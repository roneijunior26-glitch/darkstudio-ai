import shutil
import subprocess

import pytest

from app.workers import render, runner, tts
from app.workers.errors import PermanentError
from app.workers.handlers import render_final

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg ausente")


def test_split_phrases_respects_punctuation_and_size():
    p = render.split_phrases("Em 1986 um farol abandonado na costa da Noruega voltou a emitir luz. Ninguem sabia.")
    assert p[-1] == "Ninguem sabia." and all(len(x.split()) <= 7 for x in p)


def test_ass_timing_covers_full_duration():
    ass = render.build_ass("Uma frase curta. Outra frase um pouco maior aqui.", 10.0)
    ends = [l.split(",")[2] for l in ass.splitlines() if l.startswith("Dialogue")]
    assert ends[-1] == "0:00:10.00"


def test_ass_escapes_override_braces():
    assert "{" not in render.build_ass("texto {b}x{/b}", 2.0).split("[Events]")[1].split("Default,,0,0,0,,")[1]


@pytest.mark.parametrize("cam", ["slow_zoom_in", "slow_zoom_out", "pan_left", "pan_right", "static", "desconhecido"])
def test_zoompan_has_size_and_frames(cam):
    z = render.zoompan(cam, 90)
    assert "d=90" in z and "s=1920x1080" in z


class Db:
    def __init__(self, scenes):
        self.scenes, self.updates, self.inserted, self.rows = scenes, [], [], {}

    def select(self, table, q=""):
        if table == "projects":
            return [{"title": "Meu: Vídeo/Teste?", **getattr(self, "proj", {})}]
        if table == "music_assets":
            return getattr(self, "music", [])
        return self.scenes

    def insert(self, table, rows):
        self.rows.setdefault(table, []).extend(rows)
        return [{**r, "id": f"{table}-id"} for r in rows]

    def update(self, table, q, v):
        self.updates.append(v)

    def insert_ignore(self, table, rows, conflict):
        self.inserted += rows


def sc(i, img=True, aud=True):
    return {"id": f"s{i}", "position": i, "narration_text": f"Cena {i}. Texto de teste da narracao.", "camera_move": "slow_zoom_in",
            "transition": "fade", "duration_s": 2.0, "image": {"storage_key": f"i{i}"} if img else None,
            "audio": {"storage_key": f"a{i}"} if aud else None}


def test_missing_assets_raise_retryable_error():
    with pytest.raises(RuntimeError, match="sem imagem"):
        render_final.run({"project_id": "p"}, Db([sc(1), sc(2, img=False)]), lambda b, k: b"", clip_fn=lambda *a: 1.0)


def test_no_scenes_is_permanent():
    with pytest.raises(PermanentError):
        render_final.run({"project_id": "p"}, Db([]), lambda b, k: b"")


def test_enqueue_render_only_when_all_ready():
    t = {"type": "generate_audio", "project_id": "p", "user_id": "u"}
    db = Db([{"image_asset_id": "a", "audio_asset_id": None}])
    runner.enqueue_render_if_ready(db, t)
    assert db.inserted == []
    db = Db([{"image_asset_id": "a", "audio_asset_id": "b"}])
    runner.enqueue_render_if_ready(db, t)
    assert db.inserted[0]["type"] == "render_final" and db.inserted[0]["idempotency_key"] == "render:p"
    runner.enqueue_render_if_ready(Db([]), {"type": "split_scenes", "project_id": "p", "user_id": "u"})


@needs_ffmpeg
def test_full_render_with_real_ffmpeg(tmp_path):
    imgs = {}
    for i in (1, 2):
        f = tmp_path / f"i{i}.jpg"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc2=s=1024x1024:d=1", "-frames:v", "1", str(f)], check=True)
        imgs[f"i{i}"] = f.read_bytes()
    wav = tts.pcm_to_wav(b"\x10\x00" * 48000, 24000)  # 2 s
    store = {**imgs, "a1": wav, "a2": wav}
    db = Db([sc(1), sc(2)])
    pub = lambda path, name: {"backend": "gdrive", "key": "drive123", "url": "https://drive/x", "name": name}
    res = render_final.run({"project_id": "p", "user_id": "u"}, db, lambda b, k: store[k], outdir=str(tmp_path / "out"), publish=pub)
    assert res["scenes"] == 2 and res["duration_s"] == 4.6
    out = tmp_path / "out" / "p.mp4"
    info = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,width,height,r_frame_rate", "-of", "csv=p=0", str(out)],
                          capture_output=True, text=True).stdout
    assert "h264,1920,1080,30/1" in info and "aac" in info
    assert db.updates[0]["status"] == "rendering" and db.updates[-1]["status"] == "awaiting_approval"
    assert res["stored_in"] == "gdrive"
    asset = db.rows["media_assets"][0]
    assert asset["kind"] == "export" and asset["storage_key"] == "drive123" and asset["bytes"] == out.stat().st_size
    assert db.rows["project_exports"][0]["asset_id"] == "media_assets-id"


def test_safe_name_and_default_publish_fallback(monkeypatch, tmp_path):
    assert render_final.safe_name("Meu: Vídeo/Teste?") == "Meu Vídeo Teste"[:0] + "Meu VídeoTeste"
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.setenv("GITHUB_RUN_ID", "42")
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    r = render_final.default_publish(tmp_path / "x.mp4", "x.mp4")
    assert r == {"backend": "github_artifact", "key": "video-42", "url": "https://github.com/o/r/actions/runs/42"}


def test_default_publish_drive_failure_falls_back(monkeypatch, tmp_path):
    from app.workers import gdrive
    for k in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN"):
        monkeypatch.setenv(k, "x")
    monkeypatch.setenv("GITHUB_RUN_ID", "7")
    monkeypatch.setattr(gdrive, "upload", lambda *a, **k: (_ for _ in ()).throw(gdrive.DriveError("boom")))
    assert render_final.default_publish(tmp_path / "x.mp4", "x.mp4")["backend"] == "github_artifact"
    f = tmp_path / "y.mp4"; f.write_bytes(b"1")
    monkeypatch.setattr(gdrive, "upload", lambda *a, **k: {"id": "D", "link": "L", "bytes": 1})
    assert render_final.default_publish(f, "y.mp4") == {"backend": "gdrive", "key": "D", "url": "L"}
    assert not f.exists()


def test_pick_music_rules():
    db = Db([])
    assert render_final.pick_music(db, "u", {"music_enabled": False}) is None
    assert render_final.pick_music(db, "u", {}) is None
    db.music = [{"name": "a", "storage_key": "k1"}, {"name": "sem", "storage_key": None}]
    assert render_final.pick_music(db, "u", {}) == {"name": "a", "storage_key": "k1"}
    assert render_final.pick_music(db, "u", {"music_id": "x"})["storage_key"] == "k1"
    assert render_final.pick_music(db, "u", {"music_enabled": False}) is None


@needs_ffmpeg
def test_render_mixes_music_and_survives_bad_track(tmp_path):
    def mk(name, args):
        f = tmp_path / name
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args, str(f)], check=True)
        return f.read_bytes()
    store = {"i1": mk("i.jpg", ["-f", "lavfi", "-i", "testsrc2=s=1024x1024:d=1", "-frames:v", "1"]),
             "a1": tts.pcm_to_wav(b"\x10\x00" * 48000, 24000),
             "m_ok": mk("m.mp3", ["-f", "lavfi", "-i", "sine=f=220:d=2"]), "m_bad": b"nao e audio"}
    for key, ok in (("m_ok", True), ("m_bad", False)):
        db = Db([sc(1)])
        db.music = [{"name": "t", "storage_key": key}]
        res = render_final.run({"project_id": "p", "user_id": "u"}, db, lambda b, k: store[k], outdir=str(tmp_path / key),
                               publish=lambda p, n: {"backend": "x", "key": "k", "url": None})
        out = tmp_path / key / "p.mp4"
        assert out.stat().st_size > 0 and abs(res["duration_s"] - 2.3) < 0.1
        probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout
        assert "video" in probe and "audio" in probe
