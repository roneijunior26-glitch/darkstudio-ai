import pytest

from app.workers import runner, tts
from app.workers.errors import PermanentError
from app.workers.handlers import voice_preview as vp

WAV = tts.pcm_to_wav(b"\x00\x00" * 2400, 24000)


class Db:
    def __init__(self, rows):
        self.rows, self.uploads = rows, []

    def select(self, table, q=""):
        return self.rows

    def upload(self, *a):
        self.uploads.append(a)


def test_uploads_sample_in_user_voices_folder():
    db = Db([{"engine": "kokoro", "model_ref": "pm_alex", "speed": 1}])
    seen = []
    res = vp.run({"user_id": "u", "payload": {"voice_id": "v"}}, db, lambda text, voice: seen.append((text, voice)) or WAV)
    assert db.uploads[0][:2] == ("media", "u/voices/v.wav") and res["bytes"] == len(WAV)
    assert "espaço" in seen[0][0]


def test_unknown_voice_is_permanent():
    with pytest.raises(PermanentError):
        vp.run({"user_id": "u", "payload": {"voice_id": "v"}}, Db([]), lambda *a: WAV)
    with pytest.raises(PermanentError):
        vp.run({"user_id": "u", "payload": {}}, Db([{"engine": "x"}]), lambda *a: WAV)


def test_registered_in_runner():
    assert "voice_preview" in runner.handlers(object())
