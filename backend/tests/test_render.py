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
        self.scenes, self.updates, self.inserted = scenes, [], []

    def select(self, table, q=""):
        return self.scenes

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
    res = render_final.run({"project_id": "p"}, db, lambda b, k: store[k], outdir=str(tmp_path / "out"))
    assert res["scenes"] == 2 and res["duration_s"] == 4.6
    out = tmp_path / "out" / "p.mp4"
    info = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,width,height,r_frame_rate", "-of", "csv=p=0", str(out)],
                          capture_output=True, text=True).stdout
    assert "h264,1920,1080,30/1" in info and "aac" in info
    assert db.updates[0]["status"] == "rendering" and db.updates[-1]["status"] == "awaiting_approval"
